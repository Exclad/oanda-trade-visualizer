# --- Imports ---
import configparser                  # For reading the configuration file (API keys)
from datetime import datetime, timedelta, timezone # For handling dates and times
from zoneinfo import ZoneInfo        # For more robust timezone handling (like 'Asia/Singapore')

# Third-party libraries
import requests                      # For making HTTP requests to Oanda
import pandas as pd                  # For data manipulation and analysis (DataFrames)
import plotly.express as px          # For creating interactive charts
import plotly.io as pio              
import streamlit as st               # For creating the web application interface
import investpy                      # For fetching economic calendar data
import pytz                          # For the list of all timezones
import os                            # Provides functions to interact with the OS (e.g., os.path.exists)
import time                          # Provides time-related functions (e.g., time.sleep)

# --- Function to create the config file ---
def create_config(account_id, access_token, environment):
    """
    Creates and saves the config.ini file with the user-provided credentials.
    """
    # Initialize a new config parser object in memory
    config = configparser.ConfigParser()
    # Create a new section named '[OANDA]'
    config['OANDA'] = {
        'ACCOUNT_ID': account_id,
        'ACCESS_TOKEN': access_token,
        'ENVIRONMENT': environment
    }
    # Open 'config.ini' in 'write' mode ('w'). This creates the file or overwrites it.
    with open('config.ini', 'w') as configfile:
        # Write the in-memory config (with the [OANDA] section) to the file
        config.write(configfile)

# --- Configuration Loading ---

def get_config():
    """
    Reads API credentials and settings from the 'config.ini' file.
    Raises FileNotFoundError if the file or the 'OANDA' section is missing.
    Raises ValueError if any required keys are missing.
    """
    config_file = 'config.ini'
    config = configparser.ConfigParser()
    
    # Check 1: Does the file exist?
    # Use the 'os' library to check the file path.
    if not os.path.exists(config_file):
        # If not, stop and "raise" an error. This error will be "caught"
        # by the 'try...except' block in our main() function.
        raise FileNotFoundError(f"Config file '{config_file}' not found.")

    # If the file exists, read its contents into the config parser
    config.read(config_file)

    # Check 2: Does the 'OANDA' section exist?
    if 'OANDA' not in config:
        # If the section is missing, we also raise an error to trigger the setup.
        raise FileNotFoundError(f"Config file '{config_file}' is missing the '[OANDA]' section.")

    # Check 3: Are all required keys present within the [OANDA] section?
    if 'ACCOUNT_ID' not in config['OANDA'] or 'ACCESS_TOKEN' not in config['OANDA'] or 'ENVIRONMENT' not in config['OANDA']:
         # If not, raise a ValueError, which will also be caught by our 'try...except' block.
         raise ValueError(f"Config file '{config_file}' is missing a required key (ACCOUNT_ID, ACCESS_TOKEN, or ENVIRONMENT).")

    # Return the 'OANDA' section containing credentials
    return config['OANDA']

# --- Data Fetching Functions ---

# Use Streamlit's caching to avoid re-fetching data on every interaction.
# The cache is invalidated if 'refresh_key' changes (triggered by the refresh button).
@st.cache_data
def get_account_summary(refresh_key):
    """
    Connects to the Oanda API and fetches the basic account summary.
    Used for displaying live balance, P/L, margin, and getting the last transaction ID.
    Cache depends on 'refresh_key'.
    """
    print(f"RUNNING: get_account_summary() with key: {refresh_key}") # Debug print for terminal
    try:
        # Load API credentials from config file
        config = get_config()
        account_id = config['ACCOUNT_ID']
        access_token = config['ACCESS_TOKEN']
        environment = config['ENVIRONMENT']

        # Determine the correct API base URL (live or practice)
        base_url = "https://api-fxtrade.oanda.com" if environment == 'live' else "https://api-fxpractice.oanda.com"
        # Set required headers for Oanda API authentication
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # Construct the API endpoint URL for account summary
        summary_url = f"{base_url}/v3/accounts/{account_id}/summary"
        # Make the GET request to the Oanda API
        summary_response = requests.get(summary_url, headers=headers)
        summary_response.raise_for_status() # Automatically check for HTTP errors (like 401, 404)
        # Return the JSON response (account details)
        return summary_response.json()

    except Exception as e:
        # Display error in the Streamlit app if fetching fails
        st.error(f"Error fetching account summary: {e}")
        return None # Return None to indicate failure

# Use caching, invalidated by refresh_key or changes in last_transaction_id.
@st.cache_data
def fetch_trade_history(refresh_key, last_transaction_id):
    """
    Fetches all transactions for the account from ID 1 up to the provided last_transaction_id.
    Uses pagination (requests chunks of 1000) to ensure all data is retrieved.
    Processes transactions to extract details for closed trades (with realized P/L)
    and includes account balance after the trade if available.
    Cache depends on 'refresh_key' and 'last_transaction_id'.
    """
    print(f"RUNNING: fetch_trade_history() with key: {refresh_key}, up to ID: {last_transaction_id}")

    # Load API credentials
    config = get_config()
    account_id = config['ACCOUNT_ID']
    access_token = config['ACCESS_TOKEN']
    environment = config['ENVIRONMENT']

    # Set up API connection details
    base_url = "https://api-fxtrade.oanda.com" if environment == 'live' else "https://api-fxpractice.oanda.com"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # --- Pagination Logic ---
    # We must fetch transactions in chunks as the API limits responses (e.g., to 1000)
    all_transactions = []           # List to store all fetched transactions
    current_from_id = 1             # Starting transaction ID for the first chunk
    page_size = 1000                # Oanda API limit per request
    true_last_id = int(last_transaction_id) # Ensure the target ID is an integer

    print("\n--- Fetching transactions in chunks... ---")
    # Loop until we've fetched transactions beyond the last known ID
    while current_from_id <= true_last_id:
        # Determine the end ID for the current chunk (don't exceed true_last_id)
        current_to_id = min(current_from_id + page_size - 1, true_last_id)
        print(f"Fetching chunk: IDs {current_from_id} to {current_to_id}...")

        # Construct the API endpoint URL for fetching a range of transactions by ID
        transactions_url = f"{base_url}/v3/accounts/{account_id}/transactions/idrange"
        # Set the 'from' and 'to' parameters for the API request
        params = {"from": str(current_from_id), "to": str(current_to_id)}

        # Make the GET request
        response = requests.get(transactions_url, headers=headers, params=params)
        response.raise_for_status() # Check for HTTP errors
        data = response.json()      # Parse the JSON response

        # Extract the list of transactions from the response
        chunk_transactions = data.get('transactions', [])
        if not chunk_transactions:
            # Stop if the API returns an empty list (shouldn't happen before reaching last_id)
            break
        # Add the fetched transactions to our main list
        all_transactions.extend(chunk_transactions)
        # Set the starting ID for the next chunk
        current_from_id = current_to_id + 1
    print(f"SUCCESS! Fetched a total of {len(all_transactions)} transactions.")
    # --- End Pagination Logic ---

    # --- Process Fetched Transactions ---
    trade_data = [] # List to store processed data for closed trades
    # Loop through every transaction fetched
    for t in all_transactions:
        # Check if the transaction has a 'pl' field (Profit/Loss) and it's not zero.
        # This is our primary filter for identifying a "closed trade" transaction.
        if 'pl' in t and float(t['pl']) != 0:
            # Determine if the original trade was Buy or Sell based on the closing units
            # Oanda uses negative units for closing a Buy trade, positive for closing a Sell.
            trade_type = 'Buy' if float(t.get('units', 0)) < 0 else 'Sell'

            # Try to get the account balance recorded *after* this transaction occurred.
            balance_after_trade = t.get('accountBalance', None)
            if balance_after_trade:
                balance_after_trade = float(balance_after_trade)
            else:
                # Use pandas Not Available (NA) if balance is missing
                balance_after_trade = pd.NA

            # Append the relevant details to our trade_data list
            trade_data.append({
                "Date": t['time'],                  # Timestamp of the transaction (closing time)
                "Instrument": t['instrument'],      # Trading instrument (e.g., EUR_USD)
                "Buy/Sell": trade_type,             # Original trade direction (Buy or Sell)
                "Amount": abs(float(t.get('units', 0))),# Size of the closed trade (absolute value)
                "Profit/Loss": float(t['pl']),      # Realized profit or loss for this trade
                "Account Balance": balance_after_trade  # Account balance after this transaction
            })

    if not trade_data:
        # Handle case where no closed trades were found
        print("\nNo completed trades with P/L found in this transaction range.")
        return None # Return None to indicate no data

    # --- Convert List to DataFrame and Clean Data ---
    
    # Convert the list of trade data into a pandas DataFrame
    df = pd.DataFrame(trade_data)
    # Convert the 'Date' column from string to timezone-aware datetime objects (UTC initially)
    # Oanda always returns datetimes in UTC.
    df['Date'] = pd.to_datetime(df['Date'])
    # Ensure 'Profit/Loss' is a float
    df['Profit/Loss'] = df['Profit/Loss'].astype(float)
    # Convert 'Account Balance' to numeric, setting errors='coerce' turns non-numeric values into NA
    df['Account Balance'] = pd.to_numeric(df['Account Balance'], errors='coerce')

    # Sort the DataFrame by Date in descending order (most recent first) for display later
    df = df.sort_values(by='Date', ascending=False)
    # Return the processed DataFrame
    return df

# Use caching with a Time-To-Live (TTL) of 900 seconds (15 minutes).
# This means the app will only re-fetch events if the last fetch was > 15 mins ago.
@st.cache_data(ttl=900)
def fetch_ff_events():
    """
    Fetches, parses, and standardizes economic events from 'investpy'.
    - Assumes incoming times from investpy are localized to 'Asia/Singapore'.
    - Stores all times as timezone-aware UTC.
    - Sorts chronologically.
    """
    print("RUNNING: fetch_ff_events() [using investpy]")
    
    event_list = []
    
    # --- Timezone Assumption ---
    # We assume 'investpy' returns times already localized to the machine's timezone.
    # Source Timezone kept as Singapore.
    try:
        source_timezone = pytz.timezone('Asia/Singapore')
    except pytz.UnknownTimeZoneError:
        print("ERROR: 'Asia/Singapore' timezone not found. Defaulting to UTC.")
        source_timezone = pytz.utc
    
    try:
        # Fetch the calendar data from investpy
        df_invest = investpy.economic_calendar() 
        
        if df_invest.empty:
            print("DEBUG: investpy returned no events for today.")
            return None

        # Loop through each row (event) returned by the library
        for index, row in df_invest.iterrows():
            event_time_str = row['time']
            event_date_str = row['date']
            
            # --- 1. Parse Time ---
            # This logic handles the inconsistent time formats from the library
            
            if event_time_str.lower() == "all day":
                event_time_str = "00:00"

            try:
                # 1. Create the full datetime string (e.g., "01/11/2025 08:00")
                dt_str = f"{event_date_str} {event_time_str}"
                
                # 2. Create a "naive" datetime object (no timezone info)
                naive_dt = datetime.strptime(dt_str, '%d/%m/%Y %H:%M')
                
                # 3. Localize this naive time, telling it "this time is in SGT"
                local_dt = source_timezone.localize(naive_dt)
                
                # 4. Convert this SGT-aware time to standard UTC for storage.
                #    This allows us to convert it to *any* user-selected timezone later.
                event_time_utc = local_dt.astimezone(pytz.utc)
                
            except Exception as e:
                # Skip if time is malformed (e.g., "Tentative")
                print(f"Skipping event with unparsed time/date: {row['event']} ({e})")
                continue

            # --- 2. Determine Status ---
            now_utc = datetime.now(timezone.utc)
            event_status = "Passed" if event_time_utc < now_utc else "Upcoming"

            # --- 3. Parse Impact ---
            # Standardize the string (e.g., "medium" -> "Medium")
            impact_str = str(row.get('importance', 'N/A')).title() 
            # Map the string to our standard categories
            impact_map = {"High": "High", "Medium": "Medium", "Low": "Low"}
            impact = impact_map.get(impact_str, "N/A")

            # --- 4. Get Currency ---
            # Safely handle 'None' values for currency
            currency_val = row.get('currency') # This might be 'USD' or it might be None
            if currency_val is None:
                currency_code = "N/A"
            else:
                currency_code = currency_val.upper()

            # Add the processed event to our list
            event_list.append({
                "Time": event_time_utc,         # Standardized UTC datetime object
                "Status": event_status,         # "Upcoming" or "Passed"
                "Event": row.get('event', 'N/A'),
                "Currency": currency_code,
                "Impact": impact,
            })

        if not event_list:
            print("DEBUG: Data was processed, but event_list is still empty.")
            return None 

        # Convert the list to a DataFrame
        df = pd.DataFrame(event_list)
        
        # Sort by Time (chronologically)
        df = df.sort_values(by="Time", ascending=True)
        
        return df

    except Exception as e:
        # Catch-all for errors during the fetch or processing
        st.error(f"An unexpected error occurred in fetch_ff_events: {e}")
        print(f"ERROR: Unexpected exception: {e}")
        import traceback
        traceback.print_exc()
        return None

# --- Data Processing Function ---
def calculate_statistics(df, df_sorted_for_charts):
    """
    Calculates various performance statistics based on the filtered trade data.
    
    Args:
        df (pd.DataFrame): The filtered trade DataFrame (used for simple stats).
        df_sorted_for_charts (pd.DataFrame): A chronologically-sorted DataFrame
            containing the 'Cumulative P/L' column. This is required
            for the max drawdown calculation.
    """
    stats = {} # Dictionary to hold the calculated statistics

    # --- Basic Performance Metrics ---
    stats['total_pl'] = df['Profit/Loss'].sum() # Net Profit/Loss

    # Separate winning and losing trades
    wins_df = df[df['Profit/Loss'] > 0]
    losses_df = df[df['Profit/Loss'] < 0]

    # Counts
    stats['win_count'] = len(wins_df)
    stats['loss_count'] = len(losses_df)
    stats['total_trades'] = stats['win_count'] + stats['loss_count']

    # Win Rate (%)
    stats['win_rate'] = (stats['win_count'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0

    # Average Win/Loss values
    stats['avg_win'] = wins_df['Profit/Loss'].mean() if stats['win_count'] > 0 else 0
    stats['avg_loss'] = losses_df['Profit/Loss'].mean() if stats['loss_count'] > 0 else 0

    # Most Traded Instrument
    stats['most_traded'] = df['Instrument'].mode()[0] if not df.empty else "N/A"

    # --- Ratios ---
    gross_profit = wins_df['Profit/Loss'].sum()      # Sum of all positive P/L
    gross_loss = abs(losses_df['Profit/Loss'].sum())  # Sum of absolute values of negative P/L

    # Profit Factor (Gross Profit / Gross Loss)
    # Handle cases with zero loss (infinite PF) or zero profit/loss
    stats['profit_factor'] = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0)

    # Win/Loss Ratio (Number of Wins / Number of Losses)
    # Handle cases with zero losses (infinite ratio) or zero wins/losses
    stats['win_loss_ratio'] = (stats['win_count'] / stats['loss_count']) if stats['loss_count'] > 0 else (float('inf') if stats['win_count'] > 0 else 0)

    # --- Extremes ---
    stats['largest_win'] = wins_df['Profit/Loss'].max() if stats['win_count'] > 0 else 0    # Biggest single win
    stats['largest_loss'] = losses_df['Profit/Loss'].min() if stats['loss_count'] > 0 else 0   # Biggest single loss (most negative)

    # --- Max Drawdown Calculation ---
    # This is the most complex stat. It finds the biggest drop from a peak.
    # We use the pre-calculated 'Cumulative P/L' column from the sorted DataFrame
    if 'Cumulative P/L' in df_sorted_for_charts.columns:
        cumulative_pl = df_sorted_for_charts['Cumulative P/L']
        # Include a starting point of 0 before the first trade
        cumulative_pl_with_start = pd.concat([pd.Series([0]), cumulative_pl], ignore_index=True)

        # Find the running maximum (peak) P/L up to each point
        running_max = cumulative_pl_with_start.cummax()
        # Calculate the drawdown (difference between running peak and current P/L)
        drawdown = running_max - cumulative_pl_with_start
        # Find the maximum value in the drawdown series
        max_drawdown_value = drawdown.max()

        # Calculate Max Drawdown Percentage relative to the peak it dropped from
        if not drawdown.empty and drawdown.max() > 0: # Check if drawdown exists
              peak_at_max_drawdown = running_max[drawdown.idxmax()] # Find peak before max drop
              if peak_at_max_drawdown > 0: # Avoid division by zero
                  max_drawdown_percent = (max_drawdown_value / peak_at_max_drawdown) * 100
              else:
                  max_drawdown_percent = 0 # Define as 0% if drop happens from 0 or negative peak
        else: # Handle case with no drawdown (e.g., only wins or no trades)
              max_drawdown_value = 0
              max_drawdown_percent = 0

        stats['max_drawdown_value'] = max_drawdown_value
        stats['max_drawdown_percent'] = max_drawdown_percent
    else:
        # Set defaults if 'Cumulative P/L' column is missing
        stats['max_drawdown_value'] = 0
        stats['max_drawdown_percent'] = 0

    # Return the dictionary containing all calculated statistics
    return stats

# --- Helper function to calculate preset date ranges ---
def calculate_preset_dates(preset, min_hist_date, today):
    """
    Calculates the start and end date objects based on the selected preset string.
    
    Args:
        preset (str): The string from the radio button (e.g., "Last 7 Days").
        min_hist_date (date): The earliest date from trade history.
        today (date): The current date.
        
    Returns:
        (date, date): A tuple containing the (start_date, end_date).
    """
    start_dt, end_dt = min_hist_date, today # Default to 'All Time'

    if preset == "Year-to-Date (YTD)":
        start_dt = datetime(today.year, 1, 1).date()
    elif preset == "This Month":
        start_dt = today.replace(day=1)
    elif preset == "Last Month":
        first_day_current = today.replace(day=1)
        last_day_last = first_day_current - timedelta(days=1)
        start_dt = last_day_last.replace(day=1)
        end_dt = last_day_last # End date is the last day of the previous month
    elif preset == "Last 7 Days":
        start_dt = today - timedelta(days=6) # Start date is 6 days before today

    return start_dt, end_dt # Return tuple (start_date, end_date)

# --- Main Streamlit Application Logic ---
def main():
    # Configure the page appearance (wide layout, title in browser tab)
    st.set_page_config(page_title="Oanda Trading Dashboard", layout="wide")
    # Display the main title of the dashboard
    st.title("My Oanda Trading Dashboard 📈")

    # --- Initialize Streamlit Session State ---
    # Session state holds variables that persist between user interactions (reruns).
    # This is crucial for keeping track of filters, toggle states, and dates.
    # We must initialize them at the start to prevent 'KeyError' on first run.
    if "refresh_key" not in st.session_state: 
        st.session_state.refresh_key = datetime.now()
    if "selected_instruments" not in st.session_state: 
        st.session_state.selected_instruments = []
    if "show_balance_markers" not in st.session_state: 
        st.session_state.show_balance_markers = False
    if "show_pl_markers" not in st.session_state: 
        st.session_state.show_pl_markers = False
    
    # 'filter_' dates are what the app *actually* uses to filter the DataFrame
    if "filter_start_date" not in st.session_state: 
        st.session_state.filter_start_date = None
    if "filter_end_date" not in st.session_state: 
        st.session_state.filter_end_date = datetime.now().date()
        
    # 'custom_' dates just store the state of the 'Custom' date input widgets
    if "custom_start_date" not in st.session_state: 
        st.session_state.custom_start_date = None
    if "custom_end_date" not in st.session_state: 
        st.session_state.custom_end_date = datetime.now().date()
        
    # 'date_preset' stores the currently active radio button choice
    if "date_preset" not in st.session_state: 
        st.session_state.date_preset = "All Time"

    # --- Sidebar Section: Data Control & Filters ---
    st.sidebar.header("Data Control")
    # Refresh Button: Clears caches and resets session state to trigger full data reload
    if st.sidebar.button("Refresh Live Data"):
        st.cache_data.clear() # Clear function caches (@st.cache_data)
        st.session_state.clear() # Clear all variables stored in session state
        
        # Re-initialize essential state variables after clearing
        st.session_state.refresh_key = datetime.now()
        st.session_state.selected_instruments = []
        st.session_state.show_balance_markers = False
        st.session_state.show_pl_markers = False
        st.session_state.filter_start_date = None # Reset dates
        st.session_state.filter_end_date = datetime.now().date()
        st.session_state.custom_start_date = None
        st.session_state.custom_end_date = datetime.now().date()
        st.session_state.date_preset = "All Time"
        st.rerun() # Force Streamlit to rerun the script immediately
        
    # Read the current refresh key (used to bust caches)
    refresh_key = st.session_state.refresh_key

    try: # Main error handling block for the app
        # --- Fetch Live Data (using cached functions) ---
        config = get_config() # Get API config
        summary_response = get_account_summary(refresh_key) # Fetch latest account summary
        if summary_response is None:
            st.stop() # Stop execution if summary fails (error already shown in function)

        # Extract key summary details
        last_id = summary_response['account']['lastTransactionID']
        account_balance = float(summary_response['account']['balance'])
        account_pl = float(summary_response['account']['pl']) # Unrealized P/L
        margin_avail = float(summary_response['account']['marginAvailable'])

        # --- Display Account Header ---
        st.header(f"Account Summary ({config['ACCOUNT_ID']})")
        st.sidebar.info(f"Last Transaction ID: {last_id}") # Show last ID in sidebar
        # Use columns for layout
        col1, col2, col3 = st.columns(3)
        col1.metric("Balance (SGD)", f"${account_balance:,.2f}")
        col2.metric("Unrealized P/L (SGD)", f"${account_pl:,.2f}")
        col3.metric("Margin Available (SGD)", f"${margin_avail:,.2f}")

        # --- Economic Events Section ---
        st.markdown("---") 
        st.header("Today's Economic Events 📰") 

        # --- 1. Timezone Selectbox ---
        all_timezones = pytz.all_timezones
        try:
            # Default to 'Asia/Singapore', find its index
            default_ix = all_timezones.index('Asia/Singapore')
        except ValueError:
            default_ix = 0 # Fallback if 'Asia/Singapore' isn't found
            
        st.markdown("Select your timezone:")
        # Create the dropdown, its value is stored in 'user_timezone'
        user_timezone = st.selectbox(
            label="Select your timezone:",
            options=all_timezones,
            index=default_ix,
            label_visibility="collapsed" # Hides the label "Select your timezone:"
        )
        
        # Helper for impact emojis
        def map_impact_to_emoji(impact):
            if impact == "High": return "🔴 High"
            if impact == "Medium": return "🟠 Medium"
            if impact == "Low": return "🟡 Low"
            return "⚪️ N/A"

        # Styling function for 'Passed' events
        def style_passed_events(row):
            """Applies CSS to de-emphasize 'Passed' events."""
            if row.Status == 'Passed':
                # CSS for grey text with a strikethrough
                return ['color: #888888; text-decoration: line-through;'] * len(row)
            else:
                # No style for 'Upcoming' rows
                return [''] * len(row)

        # Fetch the event data
        events_df = fetch_ff_events()

        # Only display the section if events were successfully fetched
        if events_df is not None and not events_df.empty:
            
            # --- 2. Create filter widgets (Toggle and Currency Multiselect) ---
            
            # Get a sorted list of unique currencies from the data
            all_currencies = sorted(events_df['Currency'].unique())
            
            # Create two columns for the filters to sit side-by-side
            col1, col2 = st.columns(2)
            
            with col1:
                # The toggle goes in the first column
                show_only_upcoming = st.toggle("Show only upcoming events", value=True)
            
            with col2:
                # The new currency multiselect goes in the second column
                selected_currencies = st.multiselect(
                    "Filter by currency:",
                    options=all_currencies,
                    placeholder="Filter by currency (optional)",
                    label_visibility="collapsed" # Hides the label
                )

            # --- 3. Process and Filter the DataFrame ---
            # Create a copy to avoid changing the cached data
            df_events_display = events_df.copy()

            # Convert Time to Selected Timezone
            try:
                # Convert the 'Time' (which is UTC) to the user's selected timezone
                df_events_display['Time'] = df_events_display['Time'].dt.tz_convert(user_timezone)
            except Exception as e:
                st.error(f"Could not convert event time to {user_timezone}: {e}")
                
            # Format time as a string (e.g., "01/11 (Sat) 14:00")
            df_events_display['Time'] = df_events_display['Time'].dt.strftime('%d/%m (%a) %H:%M')
            # Apply emoji formatting to the 'Impact' column
            df_events_display['Impact'] = df_events_display['Impact'].apply(map_impact_to_emoji)
            
            # Select and reorder columns for a clean display
            df_events_display = df_events_display[['Time', 'Status', 'Currency', 'Impact', 'Event']] 
            
            # --- 4. Apply Filters ---
            
            # Start with the full processed DataFrame
            df_to_display = df_events_display
            
            # Apply toggle filter
            if show_only_upcoming:
                df_to_display = df_to_display[df_to_display['Status'] == 'Upcoming'].copy()
            
            # Apply currency filter (if any are selected)
            if selected_currencies:
                df_to_display = df_to_display[df_to_display['Currency'].isin(selected_currencies)]
            
            # --- 5. Apply Styling and Display ---
            # Apply the CSS styling function to the filtered DataFrame
            styler = df_to_display.style.apply(style_passed_events, axis=1)

            # Pass the STYLER object to st.dataframe to render it
            st.dataframe(styler, width='stretch', hide_index=True)

        else:
            st.info("No economic events found for today.")
        # --- [END Economic Events Section] ---

        # Fetch trade history (will use cache unless refresh_key or last_id changed)
        trade_df = fetch_trade_history(refresh_key, last_id)

        # --- Main Content Area (Only if trade data is available) ---
        if trade_df is not None and not trade_df.empty:

            # --- Sidebar Section: Filters ---
            st.sidebar.header("Filters")
            # Determine the absolute earliest date from trade history and today's date
            min_hist_date = trade_df['Date'].min().date()
            today = datetime.now().date()

            # Initialize filter/custom start date on the very first run after fetching data
            if st.session_state.filter_start_date is None:
                st.session_state.filter_start_date = min_hist_date
                st.session_state.custom_start_date = min_hist_date # Keep custom date synced initially

            # --- Date Preset Radio Buttons ---
            date_options = ["All Time", "Year-to-Date (YTD)", "This Month", "Last Month", "Last 7 Days", "Custom"]
            # The 'key' and 'on_change' parameters link the widget to our session state
            # and callback functions, enabling the complex filter logic.
            st.sidebar.radio(
                "Select Date Range",
                options=date_options,
                key="date_preset_radio", # Unique key to access this widget's value in state
                index=date_options.index(st.session_state.date_preset), # Set displayed selection based on state
                on_change=preset_changed_callback, # Function to call when selection changes
                args=(min_hist_date, today) # Arguments to pass to the callback
            )

            # --- Conditional Display: Preset Range Text or Custom Date Inputs ---
            # Determine if the date input widgets should be editable
            custom_disabled = st.session_state.date_preset != "Custom"

            # If a preset is active, show the calculated date range as text
            if st.session_state.date_preset != "Custom":
                start_display, end_display = calculate_preset_dates(st.session_state.date_preset, min_hist_date, today)
                st.sidebar.markdown(f"**Selected Range:**")
                start_display_str = start_display.strftime('%d/%m/%Y')
                end_display_str = end_display.strftime('%d/%m/%Y')
                st.sidebar.markdown(f"{start_display_str} to {end_display_str}")
                st.sidebar.markdown("---") # Separator
            # If "Custom" is active, show the date input widgets
            else:
                st.sidebar.markdown("---") # Separator
                st.sidebar.date_input(
                    "Start Date",
                    value=st.session_state.custom_start_date, # Display the stored custom start date
                    min_value=min_hist_date, max_value=today,
                    disabled=custom_disabled, 
                    key="start_date_input", # Unique key for this widget
                    on_change=custom_dates_changed_callback # Function to sync state if changed
                )
                st.sidebar.date_input(
                    "End Date",
                    value=st.session_state.custom_end_date, # Display the stored custom end date
                    min_value=min_hist_date, max_value=today,
                    disabled=custom_disabled, 
                    key="end_date_input", # Unique key
                    on_change=custom_dates_changed_callback # Function to sync state if changed
                )
                st.sidebar.markdown("---") # Separator


            # --- Instrument Filter ---
            all_instruments = sorted(trade_df['Instrument'].unique())
            st.sidebar.multiselect(
                "Select Instruments (optional)",
                options=all_instruments,
                key="instrument_multiselect", # Unique key
                default=st.session_state.selected_instruments, # Display current selection from state
                on_change=sync_instruments_callback # Function to update state if changed
            )


            # --- Apply Filters to Data ---
            # This is the master filter for all charts and tables.
            # We use the session state dates, which are controlled by the sidebar widgets.
            
            # 1. Localize the naive start/end dates from session state to UTC
            #    (since the trade_df['Date'] column is already in UTC)
            start_datetime_utc = pd.to_datetime(st.session_state.filter_start_date).tz_localize('UTC')
            # Add 1 day to end date and use '<' to include all times on the selected end day.
            # This ensures we get all trades on the selected end_date.
            end_datetime_utc = pd.to_datetime(st.session_state.filter_end_date + timedelta(days=1)).tz_localize('UTC')

            # 2. Filter the main DataFrame based on UTC dates
            df_filtered_utc = trade_df[(trade_df['Date'] >= start_datetime_utc) & (trade_df['Date'] < end_datetime_utc)]
            
            # 3. Apply instrument filter if any instruments are selected in state
            if st.session_state.selected_instruments:
                df_filtered_utc = df_filtered_utc[df_filtered_utc['Instrument'].isin(st.session_state.selected_instruments)].copy()
            else:
                df_filtered_utc = df_filtered_utc.copy() # Ensure it's a copy


            # --- Process and Display Filtered Results ---
            if df_filtered_utc.empty:
                # Show message if no trades match the current filters
                st.warning("No trade data found matching your filters.")
            else:
                # --- Convert Timezone for Display (for trade history) ---
                # Create a copy for display purposes and convert 'Date' column to local time (SGT)
                # This df_filtered is used for all *display* charts and tables.
                try:
                    df_filtered = df_filtered_utc.copy()
                    df_filtered['Date'] = df_filtered['Date'].dt.tz_convert('Asia/Singapore')
                except Exception as tz_error:
                    # Fallback to UTC if timezone conversion fails
                    st.error(f"Error converting timezone: {tz_error}")
                    df_filtered = df_filtered_utc

                # --- Calculate Statistics & Prepare Chart Data ---
                
                # Create a sorted version (by original UTC time) for time-series charts (Balance, Cum P/L)
                # This is crucial for calculating cumulative P/L and drawdown correctly.
                df_filtered_sorted_for_charts = df_filtered_utc.sort_values(by='Date', ascending=True).copy()
                # Calculate Cumulative P/L on the sorted data
                df_filtered_sorted_for_charts['Cumulative P/L'] = df_filtered_sorted_for_charts['Profit/Loss'].cumsum()
                
                # Calculate all statistics (including drawdown using the sorted df)
                stats = calculate_statistics(df_filtered, df_filtered_sorted_for_charts)

                # --- Prepare data for aggregation charts (using local time df) ---
                # These columns are temporary helpers for grouping data for the charts.
                df_filtered['Year'] = df_filtered['Date'].dt.year.astype(str)
                pl_by_year = df_filtered.groupby('Year')['Profit/Loss'].sum().reset_index()
                
                df_filtered['YearMonth'] = df_filtered['Date'].dt.strftime('%Y-%m')
                pl_by_month = df_filtered.groupby('YearMonth')['Profit/Loss'].sum().reset_index()
                
                # This 'Day' column is what we will add to the table below
                df_filtered['Day'] = df_filtered['Date'].dt.day_name()
                day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                pl_by_day = df_filtered.groupby('Day')['Profit/Loss'].sum().reindex(day_order).reset_index()

                # Prepare data for instrument charts
                pl_by_instrument = df_filtered.groupby('Instrument')['Profit/Loss'].sum().reset_index()
                count_by_instrument = df_filtered['Instrument'].value_counts().reset_index()
                count_by_instrument.columns = ['Instrument', 'Count']

                # --- Display Primary Statistics with Tooltips ---
                # Determine if any filters are active to adjust the title
                is_filtered = (st.session_state.filter_start_date != min_hist_date) or \
                                  (st.session_state.filter_end_date != today) or \
                                  bool(st.session_state.selected_instruments)
                stats_title = "Overall Statistics (Filtered)" if is_filtered else "Overall Statistics"
                st.header(stats_title)

                # Use a 3x3 grid layout for the metrics
                cols_row1 = st.columns(3); cols_row2 = st.columns(3); cols_row3 = st.columns(3)
                # Add help text to each metric for explanation
                cols_row1[0].metric("Total P/L (SGD)", f"${stats['total_pl']:,.2f}", help="Sum of Profit/Loss for all closed trades in the selected period.")
                cols_row1[1].metric("Total Closed Trades", stats['total_trades'], help="Total number of closed trades with realized Profit/Loss.")
                cols_row1[2].metric("Win Rate", f"{stats['win_rate']:.2f}%", help="Percentage of trades that were profitable (P/L > 0).")
                cols_row2[0].metric("Profit Factor", f"{stats['profit_factor']:.2f}", help="Gross Profit (sum of all wins) divided by Gross Loss (absolute sum of all losses). Higher is generally better (>1). 'inf' means no losses occurred.")
                cols_row2[1].metric("Win/Loss Ratio", f"{stats['win_loss_ratio']:.2f}", help="Total number of winning trades divided by the total number of losing trades. 'inf' means no losses occurred.")
                cols_row2[2].metric("Max Drawdown", f"${stats['max_drawdown_value']:,.2f} ({stats['max_drawdown_percent']:.1f}%)", help="The largest peak-to-trough decline in cumulative P/L during the period, representing the biggest unrealized loss from a high point.")
                cols_row3[0].metric("Avg Win / Avg Loss", f"${stats['avg_win']:,.2f} / ${stats['avg_loss']:,.2f}", help="Average Profit/Loss for winning trades / Average Profit/Loss for losing trades.")
                cols_row3[1].metric("Largest Win (SGD)", f"${stats['largest_win']:,.2f}", help="The single largest profit made on a closed trade.")
                cols_row3[2].metric("Largest Loss (SGD)", f"${stats['largest_loss']:,.2f}", help="The single largest loss taken on a closed trade.")


                # --- Charts Section ---
                st.header("Visualizations"); st.markdown("---") # Main section header

                # --- Account Balance Chart ---
                st.subheader("Account Balance Trend (After Trade)")
                st.session_state.show_balance_markers = st.toggle("Show Markers", value=st.session_state.show_balance_markers, key="balance_markers_toggle")
                balance_data_df = df_filtered_sorted_for_charts.dropna(subset=['Account Balance'])
                if not balance_data_df.empty:
                    min_bal = balance_data_df['Account Balance'].min(); max_bal = balance_data_df['Account Balance'].max(); padding_y = (max_bal - min_bal) * 0.1; yaxis_range_bal = [min_bal - padding_y, max_bal + padding_y]
                    min_date_bal = balance_data_df['Date'].min(); max_date_bal = balance_data_df['Date'].max(); padding_x = timedelta(days=5); xaxis_range_bal = [min_date_bal - padding_x, max_date_bal + padding_x]
                    fig_balance = px.line(balance_data_df, x='Date', y='Account Balance', title="Account Balance After Each Closed Trade", labels={'Account Balance': 'Account Balance (SGD)'}, markers=st.session_state.show_balance_markers)
                    fig_balance.update_traces(hovertemplate='Date: %{x}<br>Balance: $%{y:,.2f}')
                    fig_balance.update_layout(hovermode="x unified", yaxis_range=yaxis_range_bal, xaxis_range=xaxis_range_bal)
                    st.plotly_chart(fig_balance, use_container_width=True) # Use full width
                else:
                    st.info("Account balance data not available in transaction history for this period.")
                st.markdown("---") # Separator


                # --- Cumulative P/L Chart ---
                st.subheader("Cumulative P/L Trend")
                st.session_state.show_pl_markers = st.toggle("Show Markers", value=st.session_state.show_pl_markers, key="pl_markers_toggle")
                pl_data = df_filtered_sorted_for_charts['Cumulative P/L']; min_pl = pl_data.min(); max_pl = pl_data.max(); padding_y = max(abs(max_pl - min_pl) * 0.1, 1); yaxis_range_pl = [min_pl - padding_y, max_pl + padding_y]
                min_date_pl = df_filtered_sorted_for_charts['Date'].min(); max_date_pl = df_filtered_sorted_for_charts['Date'].max(); padding_x = timedelta(days=5); xaxis_range_pl = [min_date_pl - padding_x, max_date_pl + padding_x]
                fig_line = px.line(df_filtered_sorted_for_charts, x='Date', y='Cumulative P/L', labels={'Cumulative P/L': 'Cumulative P/L (SGD)'}, markers=st.session_state.show_pl_markers)
                fig_line.update_traces(hovertemplate='Date: %{x}<br>Cumulative P/L: $%{y:,.2f}')
                fig_line.update_layout(hovermode="x unified", yaxis_range=yaxis_range_pl, xaxis_range=xaxis_range_pl)
                st.plotly_chart(fig_line, use_container_width=True) # Use full width
                st.markdown("---") # Separator


                # --- Performance Distribution Section ---
                st.subheader("Performance Distribution")
                col1, col2 = st.columns(2)
                with col1:
                    pie_data = pd.DataFrame({'Metric': ['Wins', 'Losses'], 'Count': [stats['win_count'], stats['loss_count']]})
                    fig_pie = px.pie(pie_data, values='Count', names='Metric', title="Win/Loss Distribution", color='Metric', color_discrete_map={'Wins': 'green', 'Losses': 'red'})
                    fig_pie.update_traces(textinfo='percent+label+value') 
                    st.plotly_chart(fig_pie, use_container_width=True)
                with col2:
                    fig_hist = px.histogram(df_filtered, x="Profit/Loss", nbins=30, title="Distribution of Trade P/L", text_auto=True) 
                    fig_hist.update_traces(marker_line_color='black', marker_line_width=1, hovertemplate='P/L Range: %{x}<br>Count: %{y}') 
                    st.plotly_chart(fig_hist, use_container_width=True)
                st.markdown("---") # Separator


                # --- Instrument Analysis Section ---
                st.subheader("Instrument Analysis")
                col1, col2 = st.columns(2) 
                with col1:
                      # This bar chart shows total P/L, colored by profit (green) or loss (red)
                      fig_inst_pl = px.bar(pl_by_instrument.sort_values('Profit/Loss', ascending=False), 
                                           x='Instrument', y='Profit/Loss', color='Profit/Loss', 
                                           color_continuous_scale=px.colors.diverging.RdYlGn, 
                                           title="Total P/L by Instrument")
                      fig_inst_pl.update_traces(hovertemplate='Instrument: %{x}<br>Total P/L: $%{y:,.2f}')
                      st.plotly_chart(fig_inst_pl, use_container_width=True)
                with col2:
                      # This bar chart shows the simple count of trades per instrument
                      fig_inst_count = px.bar(count_by_instrument.sort_values('Count', ascending=False), 
                                              x='Instrument', y='Count', title="Trade Count by Instrument")
                      fig_inst_count.update_traces(hovertemplate='Instrument: %{x}<br>Count: %{y}')
                      st.plotly_chart(fig_inst_count, use_container_width=True)
                st.markdown("---") # Separator


                # --- Performance Over Time Section ---
                st.subheader("Performance Over Time")

                # Yearly P/L Bar Chart
                fig_yearly_pl = px.bar(pl_by_year, x='Year', y='Profit/Loss', title="Total P/L by Year", 
                                       color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn)
                fig_yearly_pl.update_traces(hovertemplate='Year: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_yearly_pl, use_container_width=True)

                # Monthly P/L Bar Chart
                fig_monthly_pl = px.bar(pl_by_month, x='YearMonth', y='Profit/Loss', title="Total P/L by Month", 
                                        color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, 
                                        labels={'YearMonth': 'Month'})
                fig_monthly_pl.update_traces(hovertemplate='Month: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_monthly_pl, use_container_width=True)

                # Day of Week P/L Bar Chart
                st.subheader("Performance by Day of Week", help="This chart shows the total Profit/Loss realized on each day of the week, based on the closing time of the trade in your local timezone (SGT).")
                fig_day_pl = px.bar(pl_by_day, x='Day', y='Profit/Loss', title="Total P/L by Day", 
                                    color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, 
                                    labels={'Day': 'Day'})
                fig_day_pl.update_traces(hovertemplate='Day: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_day_pl, use_container_width=True)
                
                st.markdown("---") # Separator


                # --- Filtered Trade History Table & Download ---
                st.header("Filtered Trade History")
                
                # Define the exact columns we want to show in the final table
                columns_to_show = [
                    "Date", "Day", "Instrument", "Buy/Sell", 
                    "Amount", "Profit/Loss", "Account Balance"
                ]
                
                # Filter df_filtered to only these columns for display and CSV
                # This ensures temporary columns (Year, YearMonth) are not shown
                available_columns = [col for col in columns_to_show if col in df_filtered.columns]
                
                # Create a specific DataFrame for the CSV download
                # We use df_filtered (which has SGT datetimes) for the CSV
                df_csv = df_filtered[available_columns].copy()
                csv_string = df_csv.to_csv(index=False).encode('utf-8')
                
                # Create a separate DataFrame for display (with formatted dates)
                df_display = df_filtered[available_columns].copy()
                
                # Format the 'Date' column *for display only*
                df_display['Date'] = df_display['Date'].dt.strftime('%d/%m/%Y %H:%M:%S %Z')
                
                # Display the DataFrame with formatting for P/L and Balance columns
                st.dataframe(df_display.style.format({"Profit/Loss": "{:.2f}", "Account Balance": "{:.2f}"}), width='stretch')

                # Add the download button (using the df_csv data)
                st.download_button(
                    label="📥 Download Filtered Data as CSV",
                    data=csv_string,
                    # Create a dynamic file name based on the filter dates
                    file_name=f"oanda_trades_{st.session_state.filter_start_date}_to_{st.session_state.filter_end_date}.csv",
                    mime='text/csv', # Set the file type
                )

        # --- Handle Case: No Trade Data Found ---
        else:
            st.warning("No completed trades with P/L found in your account history.")

    # --- Error Handling ---
    # This 'try' block attempts to run the main dashboard logic.
    # If get_config() fails, it raises FileNotFoundError or ValueError.
    # The 'except' block below will "catch" those specific errors.
    except (FileNotFoundError, ValueError) as e:
        # This code block only runs if the 'try' block fails with one of the specified errors.
        
        # Display the error that was raised (e.g., "Config file 'config.ini' not found.")
        st.warning(f"Configuration Error: {e}")
        # Show a friendly welcome message for the setup process
        st.header("Welcome! Please set up your Oanda Credentials")
        st.info("Your credentials will be saved locally to 'config.ini' for future use.")
        
        # Create a Streamlit Form. This groups all the inputs together.
        # The code inside the 'if submitted:' block will only run when the button is pressed.
        with st.form("config_form"):
            st.write("Enter your Oanda v20 API details below:")
            
            # --- 1. ACCOUNT ID INPUT ---
            # Use st.markdown for a bold, custom label
            st.markdown("**Oanda Account ID**")
            # Use st.write for standard-sized help text
            st.write("This is your account number, e.g., `xxx-xxx-xxxxxxx-xxx`")
            account_id = st.text_input(
                "Oanda Account ID",            # Internal label (for accessibility)
                label_visibility="collapsed",  # Hide the internal label
                placeholder="xxx-xxx-xxxxxxx-xxx"
            )

            # --- 2. API TOKEN INPUT ---
            # Use st.markdown for a bold, custom label
            st.markdown("**Oanda API Access Token**")
            # Provide a clickable link to help the user
            st.markdown("You can generate your token here: [Oanda Personal Token Hub](https://hub.oanda.com/tpa/personal_token)")
            access_token = st.text_input(
                "Oanda API Access Token",      # Internal label (for accessibility)
                type="password",               # Hides the input as the user types
                label_visibility="collapsed",  # Hide the internal label
                placeholder="Paste your API token here"
            )

            # --- 3. ENVIRONMENT SELECTION ---
            # Use st.radio for a simple, non-breakable choice
            env_choice = st.radio(
                "Select Environment",
                ("Demo (Practice)", "Live"),  # User-friendly labels
                index=0,                      # Default to "Demo"
                horizontal=True,              # Display buttons side-by-side
                help="Select 'Demo' for your practice account or 'Live' for your real trading account."
            )
            
            # The one and only button for the form
            submitted = st.form_submit_button("Save and Run Dashboard")
        
        # This 'if' block is OUTSIDE the form, but tied to the 'submitted' variable.
        # It runs only after the user clicks the "Save" button.
        if submitted:
            # Simple validation to make sure fields are not blank
            if not account_id or not access_token:
                st.error("Please fill in both Account ID and Access Token.")
            else:
                # Convert the user-friendly radio option ("Demo (Practice)")
                # into the system value ("practice") that the API expects.
                environment = 'practice' if env_choice == 'Demo (Practice)' else 'live'
                
                # Call our helper function to write the data to 'config.ini'
                create_config(account_id, access_token, environment) 
                
                # Show a temporary success message
                st.success("Configuration saved! Reloading dashboard...")
                # Pause for 2 seconds so the user can read the message
                time.sleep(2) 
                # Rerun the entire script from the top.
                # This time, get_config() will succeed, and the dashboard will load.
                st.rerun() 
    
    # This is the final 'catch-all' exception handler
    except Exception as e:
        # This catches any OTHER error that might happen during the dashboard's runtime
        # (e.g., Oanda's API is down, a bad API key was saved, a bug in a chart).
        st.error(f"An unexpected error occurred: {e}")
        # st.exception(e) prints the full error traceback for debugging.
        st.exception(e)


# --- Callback functions (Defined outside main() for clarity and scope) ---
# Callbacks are functions that run when a widget's state changes (e.g., button click)
# They are essential for linking widgets together and updating session state.

def preset_changed_callback(min_hist_date, today):
    """
    Called when the 'Select Date Range' radio button is changed.
    Updates the filter dates and custom dates in session_state.
    """
    # Get the new value selected by the user from session_state
    preset = st.session_state.date_preset_radio 
    st.session_state.date_preset = preset # Update the main preset state variable

    # If a non-custom preset was selected, calculate the corresponding dates
    if preset != "Custom":
        start_dt, end_dt = calculate_preset_dates(preset, min_hist_date, today)
        # Update the state variables that store the *active filter dates*
        st.session_state.filter_start_date = start_dt
        st.session_state.filter_end_date = end_dt
        # Also update the custom dates to match, so "Custom" starts from the preset range
        st.session_state.custom_start_date = start_dt
        st.session_state.custom_end_date = end_dt
    else:
        # If the user explicitly selected "Custom", set the active filter dates
        # to whatever is stored in the custom date state variables.
        st.session_state.filter_start_date = st.session_state.custom_start_date
        st.session_state.filter_end_date = st.session_state.custom_end_date

def custom_dates_changed_callback():
    """
    Called when the 'Start Date' or 'End Date' input widget changes.
    Syncs the custom dates back to the main filter dates.
    """
    # Update the custom date state variables from the input widget keys
    st.session_state.custom_start_date = st.session_state.start_date_input
    st.session_state.custom_end_date = st.session_state.end_date_input
    # Immediately sync the active filter dates to match the new custom dates
    st.session_state.filter_start_date = st.session_state.custom_start_date
    st.session_state.filter_end_date = st.session_state.custom_end_date
    # Ensure the preset state reflects "Custom" if it wasn't already
    st.session_state.date_preset = "Custom"


def sync_instruments_callback():
    """
    Called when the 'Select Instruments' multiselect widget changes.
    Updates the list of selected instruments in session_state.
    """
    # Update the selected instruments state variable from the multiselect widget key
    st.session_state.selected_instruments = st.session_state.instrument_multiselect

# --- Run the main function when the script is executed ---
if __name__ == "__main__":
    main()
