# --- Imports ---
import configparser                    # For reading the configuration file (API keys)
from datetime import datetime, timedelta, timezone # For handling dates and times
from zoneinfo import ZoneInfo          # For more robust timezone handling (like 'Asia/Singapore')

# Third-party libraries
import requests                        # For making HTTP requests to Oanda
import pandas as pd                    # For data manipulation and analysis (DataFrames)
import plotly.express as px            # For creating interactive charts
import plotly.io as pio                # Plotly Input/Output, for saving/displaying charts
import streamlit as st                 # For creating the web application interface
import investpy                        # For fetching economic calendar data
import pytz                            # For the list of all timezones
import os                              # Provides functions to interact with the OS (e.g., os.path.exists)
import time                            # Provides time-related functions (e.g., time.sleep)

# --- Function to create the config file ---
# Note: This function appears to be unused in the main app, but is kept.
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
    Reads API credentials based on the active environment in session_state.
    - 'live' state reads 'config.ini'
    - 'demo' state reads 'config_demo.ini'
    
    Raises FileNotFoundError if the file or the 'OANDA' section is missing.
    Raises ValueError if any required keys are missing.
    """
    
    # Get the active environment from session state. Default to 'live' if not set.
    active_env = st.session_state.get('active_environment', 'live')

    # Determine which config file to read
    if active_env == 'demo':
        config_file = 'config_demo.ini'
    else:
        config_file = 'config.ini'

    config = configparser.ConfigParser()
    
    # Check 1: Does the selected file exist?
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Config file '{config_file}' not found for {active_env} environment.")

    config.read(config_file) # Load the config file

    # Check 2: Does the 'OANDA' section exist?
    if 'OANDA' not in config:
        raise FileNotFoundError(f"Config file '{config_file}' is missing the '[OANDA]' section.")

    # Check 3: Are keys present? (Good practice)
    if 'ACCOUNT_ID' not in config['OANDA'] or 'ACCESS_TOKEN' not in config['OANDA'] or 'ENVIRONMENT' not in config['OANDA']:
         raise ValueError(f"Config file '{config_file}' is missing a required key.")
    
    # Return the 'OANDA' section containing credentials
    return config['OANDA']

def save_config(env_type, account_id, access_token):
    """
    Saves the provided credentials to the correct file ('config.ini' or 'config_demo.ini').
    """
    # Determine the correct filename and Oanda environment string ('practice' or 'live')
    if env_type == 'demo':
        config_file = 'config_demo.ini'
        environment_value = 'practice' # Oanda API refers to demo as 'practice'
    else:
        config_file = 'config.ini'
        environment_value = 'live'

    config = configparser.ConfigParser()
    # Create the [OANDA] section in the config object
    config['OANDA'] = {
        'ACCOUNT_ID': account_id,
        'ACCESS_TOKEN': access_token,
        'ENVIRONMENT': environment_value
    }
    
    # Write the config object to the determined file
    with open(config_file, 'w') as configfile:
        config.write(configfile)

def get_specific_config(env_type):
    """
    Tries to read a specific config file ('live' or 'demo')
    and returns its contents or None if it doesn't exist or is invalid.
    Used by the setup page to check file status.
    """
    if env_type == 'demo':
        config_file = 'config_demo.ini'
    else:
        config_file = 'config.ini'

    # If the file doesn't exist, return None
    if not os.path.exists(config_file):
        return None

    config = configparser.ConfigParser()
    config.read(config_file)

    # If file is missing the [OANDA] section, return None
    if 'OANDA' not in config:
        return None
        
    # If file is missing required keys, return None
    if 'ACCOUNT_ID' not in config['OANDA'] or 'ACCESS_TOKEN' not in config['OANDA']:
         return None
    
    # Return the config as a dictionary
    return dict(config['OANDA'])

def show_setup_or_edit_page():
    """
    Displays a page with forms to edit the Demo and Live credentials.
    This page is shown on first run (no configs) or when 'Edit Credentials' is clicked.
    It uses session_state 'editing_demo' and 'editing_live' to control UI.
    """
    st.header("Setup / Edit Credentials")
    st.info("Your credentials will be saved locally. You only need to fill in the account(s) you wish to use.")
    
    col1, col2 = st.columns(2)

    # --- Read existing configs for pre-filling ---
    # This checks if files exist to determine the UI state (show form vs. show buttons)
    demo_config = get_specific_config('demo')
    live_config = get_specific_config('live')
    
    # Check if we are currently in an "editing" state (set by the 'Edit' button)
    is_editing_demo = st.session_state.get('editing_demo', False)
    is_editing_live = st.session_state.get('editing_live', False)

    # --- DEMO CONFIG (Column 1) ---
    with col1:
        st.subheader("Demo Account (`config_demo.ini`)")
        
        # SHOW FORM if (file doesn't exist) OR (we are in editing mode)
        if not demo_config or is_editing_demo:
            
            # Pre-fill with existing data if we are editing
            default_id = demo_config['account_id'] if demo_config and is_editing_demo else ""
            default_token = demo_config['access_token'] if demo_config and is_editing_demo else ""

            # Use a form to capture inputs
            with st.form("demo_config_form"):
                st.markdown("**Demo Account ID**")
                account_id_demo = st.text_input("Demo Account ID", value=default_id, placeholder="xxx-xxx-xxxxxxx-xxx", label_visibility="collapsed")
                
                st.markdown("**Demo API Access Token**")
                st.markdown("[Get API Token Here](https://hub.oanda.com/tpa/personal_token)")
                access_token_demo = st.text_input("Demo API Token", value=default_token, type="password", placeholder="Paste demo token here", label_visibility="collapsed")

                submitted_demo = st.form_submit_button("Save Demo Credentials")
                
                if submitted_demo:
                    if not account_id_demo or not access_token_demo:
                        st.error("Please fill in both fields for the Demo account.")
                    else:
                        # Save the credentials to config_demo.ini
                        save_config('demo', account_id_demo, access_token_demo)
                        st.session_state.editing_demo = False # Turn off editing mode
                        st.success("Demo credentials saved!")
                        time.sleep(1) # Brief pause to show message
                        st.rerun() # Rerun the app to reflect changes
        else:
            # --- SHOW BUTTONS (File exists and we are NOT editing) ---
            st.success("Demo credentials are saved.")
            
            # Use columns to put buttons side-by-side
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                # Button to go to the dashboard using this account
                if st.button("Go to Demo Dashboard", width='stretch'):
                    st.session_state.active_environment = 'demo'
                    st.session_state.show_edit_page = False # Hide the edit page
                    st.session_state.editing_demo = False # Reset edit flags
                    st.session_state.editing_live = False # Reset edit flags
                    st.rerun() 
            with btn_col2:
                # Button to enable editing mode for Demo
                if st.button("Edit Demo Credentials", width='stretch'):
                    st.session_state.editing_demo = True
                    st.rerun()

    # --- LIVE CONFIG (Column 2) ---
    # This logic mirrors the Demo config section exactly
    with col2:
        st.subheader("Live Account (`config.ini`)")
        
        # SHOW FORM if (file doesn't exist) OR (we are in editing mode)
        if not live_config or is_editing_live:

            # Pre-fill with existing data if we are editing
            default_id = live_config['account_id'] if live_config and is_editing_live else ""
            default_token = live_config['access_token'] if live_config and is_editing_live else ""

            with st.form("live_config_form"):
                st.markdown("**Live Account ID**")
                account_id_live = st.text_input("Live Account ID", value=default_id, placeholder="xxx-xxx-xxxxxxx-xxx", label_visibility="collapsed")
                
                st.markdown("**Live API Access Token**")
                st.markdown("[Get API Token Here](https://hub.oanda.com/tpa/personal_token)")
                access_token_live = st.text_input("Live API Token", value=default_token, type="password", placeholder="Paste live token here", label_visibility="collapsed")
                
                submitted_live = st.form_submit_button("Save Live Credentials")

                if submitted_live:
                    if not account_id_live or not access_token_live:
                        st.error("Please fill in both fields for the Live account.")
                    else:
                        # Save the credentials to config.ini
                        save_config('live', account_id_live, access_token_live)
                        st.session_state.editing_live = False # Turn off editing mode
                        st.success("Live credentials saved!")
                        time.sleep(1)
                        st.rerun()
        else:
            # --- SHOW BUTTONS (File exists and we are NOT editing) ---
            st.success("Live credentials are saved.")
            
            # Use columns to put buttons side-by-side
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                # Button to go to the dashboard using this account
                if st.button("Go to Live Dashboard", width='stretch'):
                    st.session_state.active_environment = 'live'
                    st.session_state.show_edit_page = False # Hide the edit page
                    st.session_state.editing_demo = False # Reset edit flags
                    st.session_state.editing_live = False # Reset edit flags
                    st.rerun()
            with btn_col2:
                # Button to enable editing mode for Live
                if st.button("Edit Live Credentials", width='stretch'):
                    st.session_state.editing_live = True
                    st.rerun()

    st.markdown("---")
    # Show "Back" button only if this isn't the forced initial setup
    # (i.e., if at least one config file already exists)
    if live_config or demo_config:
        if st.button("Back to Dashboard"):
            st.session_state.show_edit_page = False
            # Reset editing states when going back
            st.session_state.editing_demo = False
            st.session_state.editing_live = False
            st.rerun()

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
    # This print helps debug cache invalidation
    print(f"RUNNING: get_account_summary() with key: {refresh_key}")
    try:
        # Load API credentials from the *active* config file
        config = get_config()
        account_id = config['ACCOUNT_ID']
        access_token = config['ACCESS_TOKEN']
        environment = config['ENVIRONMENT'] # 'live' or 'practice'

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
    - Stores all times as timezone-aware UTC for consistent processing.
    - Sorts chronologically.
    """
    print("RUNNING: fetch_ff_events() [using investpy]")
    
    event_list = []
    
    # --- Timezone Assumption ---
    # We assume 'investpy' returns times already localized to the machine's timezone.
    # We explicitly define this source timezone to be 'Asia/Singapore'.
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
            
            # Handle 'All Day' events by setting them to the start of the day
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
            # Compare the event's UTC time to the current UTC time
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
    gross_profit = wins_df['Profit/Loss'].sum()       # Sum of all positive P/L
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
    # session_state is used to store variables that persist between reruns,
    # such as filter values, UI states (e.g., 'editing_demo'), and cached data keys.
    if "refresh_key" not in st.session_state: 
        st.session_state.refresh_key = datetime.now()
    if "selected_instruments" not in st.session_state: 
        st.session_state.selected_instruments = []
    if "show_balance_markers" not in st.session_state: 
        st.session_state.show_balance_markers = False
    if "show_pl_markers" not in st.session_state: 
        st.session_state.show_pl_markers = False
    if "filter_start_date" not in st.session_state: 
        st.session_state.filter_start_date = None
    if "filter_end_date" not in st.session_state: 
        st.session_state.filter_end_date = datetime.now().date()
    if "custom_start_date" not in st.session_state: 
        st.session_state.custom_start_date = None
    if "custom_end_date" not in st.session_state: 
        st.session_state.custom_end_date = datetime.now().date()
    if "date_preset" not in st.session_state: 
        st.session_state.date_preset = "All Time"
    if "show_edit_page" not in st.session_state:
        st.session_state.show_edit_page = False
    if "active_environment" not in st.session_state:
        # Default to 'live' if config.ini exists, otherwise 'demo'
        st.session_state.active_environment = 'live' if os.path.exists('config.ini') else 'demo'
    if "editing_demo" not in st.session_state:
        st.session_state.editing_demo = False
    if "editing_live" not in st.session_state:
        st.session_state.editing_live = False

    # --- Check which config files exist ---
    demo_exists = os.path.exists('config_demo.ini')
    live_exists = os.path.exists('config.ini')

    # --- Handle Initial Setup & Edit Page ---
    # If no config files exist, force the setup page to show
    if not demo_exists and not live_exists:
        st.warning("Welcome! Please set up at least one account to use the dashboard.")
        st.session_state.show_edit_page = True 
    # If the 'show_edit_page' state is True (either from setup or 'Edit' button)
    if st.session_state.show_edit_page:
        show_setup_or_edit_page() # Display the setup/edit page
        st.stop() # Do not run the rest of the dashboard

    # --- Sidebar Section: Data Control & Filters ---
    st.sidebar.header("Data Control")

    # --- Account Toggle (Demo/Live) ---
    # Only show the toggle if *both* config files exist
    if demo_exists and live_exists:
        st.sidebar.subheader("Active Account")
        # Set the radio button's default based on the active session state
        default_index = 0 if st.session_state.active_environment == 'demo' else 1
        
        def toggle_changed():
            """
            Callback function when the Demo/Live radio button is changed.
            """
            new_env = st.session_state.account_toggle
            st.session_state.active_environment = "demo" if new_env == "Demo" else "live"
            # Clear all caches and reset filters when switching accounts
            st.cache_data.clear() 
            st.session_state.selected_instruments = []
            st.session_state.filter_start_date = None 
            st.session_state.filter_end_date = datetime.now().date()
            st.session_state.custom_start_date = None
            st.session_state.custom_end_date = datetime.now().date()
            st.session_state.date_preset = "All Time"
        
        st.sidebar.radio(
            "Select Account",
            ("Demo", "Live"),
            index=default_index,
            key="account_toggle",
            on_change=toggle_changed,
            horizontal=True
        )
    else:
        # If only one file exists, set the active environment automatically
        st.session_state.active_environment = 'demo' if demo_exists else 'live'
    
    # --- Edit Credentials Button ---
    # This button sets the state to show the edit page and reruns
    if st.sidebar.button("Edit Credentials", width='stretch'):
        st.session_state.show_edit_page = True
        st.rerun()

    st.sidebar.markdown("---")
        
    # Refresh Button
    # This button clears all data caches and resets filters
    if st.sidebar.button("Refresh Data", width='stretch'):
        st.cache_data.clear() # Clear all @st.cache_data functions
        st.session_state.refresh_key = datetime.now() # Update the key to trigger re-fetch
        # Reset all filters to their defaults
        st.session_state.selected_instruments = []
        st.session_state.show_balance_markers = False
        st.session_state.show_pl_markers = False
        st.session_state.filter_start_date = None
        st.session_state.filter_end_date = datetime.now().date()
        st.session_state.custom_start_date = None
        st.session_state.custom_end_date = datetime.now().date()
        st.session_state.date_preset = "All Time"
        st.rerun() 
        
    # Get the current refresh key from state (used by cached functions)
    refresh_key = st.session_state.refresh_key

    try: 
        # --- Fetch Live Data ---
        # Load the config for the *active* environment
        config = get_config() 
        # Fetch the latest account summary (cached)
        summary_response = get_account_summary(refresh_key) 
        # If fetching failed (e.g., API error), stop execution
        if summary_response is None:
            st.stop() 

        # --- Display Account Header ---
        # Extract key summary details
        last_id = summary_response['account']['lastTransactionID']
        env_label = st.session_state.active_environment.title()
        st.header(f"Account Summary ({config['account_id']} - **{env_label}**)")
        account_balance = float(summary_response['account']['balance'])
        account_pl = float(summary_response['account']['pl']) # Unrealized P/L
        margin_avail = float(summary_response['account']['marginAvailable'])

        # Display last transaction ID in the sidebar
        st.sidebar.info(f"Last Transaction ID: {last_id}") 

        # Display metrics in 3 columns
        col1, col2, col3 = st.columns(3)
        col1.metric("Balance (SGD)", f"${account_balance:,.2f}")
        col2.metric("Unrealized P/L (SGD)", f"${account_pl:,.2f}")
        col3.metric("Margin Available (SGD)", f"${margin_avail:,.2f}")

        # --- Economic Events Section ---
        st.markdown("---") 
        st.header("Today's Economic Events 📰") 
        # Get all available timezones from pytz
        all_timezones = pytz.all_timezones
        try:
            # Try to default to 'Asia/Singapore'
            default_ix = all_timezones.index('Asia/Singapore')
        except ValueError:
            default_ix = 0 # Default to the first timezone if not found
        # Timezone selector for event display
        user_timezone = st.selectbox(
            label="Select your timezone:",
            options=all_timezones,
            index=default_ix,
            label_visibility="collapsed"
        )
        
        def map_impact_to_emoji(impact):
            """Helper function to assign an emoji to the event impact."""
            if impact == "High": return "🔴 High"
            if impact == "Medium": return "🟠 Medium"
            if impact == "Low": return "🟡 Low"
            return "⚪️ N/A"
        
        def style_passed_events(row):
            """
            Helper function to style rows in the events DataFrame.
            Grays out and strikes through events that have passed.
            """
            if row.Status == 'Passed':
                # Apply style to all columns in the row
                return ['color: #888888; text-decoration: line-through;'] * len(row)
            else:
                return [''] * len(row) # No style for upcoming events
        
        # Fetch event data (cached with TTL)
        events_df = fetch_ff_events()
        
        if events_df is not None and not events_df.empty:
            # Get unique currencies for the filter
            all_currencies = sorted(events_df['Currency'].unique())
            
            # UI for event filters
            col1, col2 = st.columns(2)
            with col1:
                show_only_upcoming = st.toggle("Show only upcoming events", value=True)
            with col2:
                selected_currencies = st.multiselect(
                    "Filter by currency:",
                    options=all_currencies,
                    placeholder="Filter by currency (optional)",
                    label_visibility="collapsed"
                )
            
            # Create a copy for display formatting
            df_events_display = events_df.copy()
            
            # Convert the stored UTC time to the user's selected timezone
            try:
                df_events_display['Time'] = df_events_display['Time'].dt.tz_convert(user_timezone)
            except Exception as e:
                st.error(f"Could not convert event time to {user_timezone}: {e}")
            
            # Format time string and impact emoji for display
            df_events_display['Time'] = df_events_display['Time'].dt.strftime('%d/%m (%a) %H:%M')
            df_events_display['Impact'] = df_events_display['Impact'].apply(map_impact_to_emoji)
            # Reorder columns for display
            df_events_display = df_events_display[['Time', 'Status', 'Currency', 'Impact', 'Event']] 
            
            # Apply filters
            df_to_display = df_events_display
            if show_only_upcoming:
                df_to_display = df_to_display[df_to_display['Status'] == 'Upcoming'].copy()
            if selected_currencies:
                df_to_display = df_to_display[df_to_display['Currency'].isin(selected_currencies)]
            
            # Apply the row styling (for passed events)
            styler = df_to_display.style.apply(style_passed_events, axis=1)
            # Display the final DataFrame
            st.dataframe(styler, width='stretch', hide_index=True)
        else:
            st.info("No economic events found for today.")
        # --- [END Economic Events Section] ---

        # Fetch trade history (cached)
        trade_df = fetch_trade_history(refresh_key, last_id)

        # --- Main Content Area (Only if trade data is available) ---
        if trade_df is not None and not trade_df.empty:

            # --- Sidebar Section: Filters ---
            
            # Group all filters into an expander for a cleaner sidebar
            with st.sidebar.expander("Trade & Date Filters", expanded=True):

                # Get the date range of the entire trade history
                min_hist_date = trade_df['Date'].min().date()
                today = datetime.now().date()

                # Initialize filter dates on first run
                if st.session_state.filter_start_date is None:
                    st.session_state.filter_start_date = min_hist_date
                    st.session_state.custom_start_date = min_hist_date 

                # --- Date Preset ---
                date_options = ["All Time", "Year-to-Date (YTD)", "This Month", "Last Month", "Last 7 Days", "Custom"]
                
                # Use a selectbox for date presets
                st.selectbox(
                    "Select Date Range",
                    options=date_options,
                    key="date_preset_radio", # Key links this to the session state
                    index=date_options.index(st.session_state.date_preset), 
                    on_change=preset_changed_callback, # Callback to update dates
                    args=(min_hist_date, today) # Pass arguments to the callback
                )

                # --- Conditional Date Display ---
                # Disable custom date pickers unless "Custom" is selected
                custom_disabled = st.session_state.date_preset != "Custom"

                if st.session_state.date_preset != "Custom":
                    # If not 'Custom', show the calculated range as text
                    start_display, end_display = calculate_preset_dates(st.session_state.date_preset, min_hist_date, today)
                    st.markdown(f"**Selected Range:**")
                    start_display_str = start_display.strftime('%d/%m/%Y')
                    end_display_str = end_display.strftime('%d/%m/%Y')
                    st.markdown(f"{start_display_str} to {end_display_str}")
                else:
                    # If 'Custom', show the date input widgets
                    st.date_input(
                        "Start Date",
                        value=st.session_state.custom_start_date,
                        min_value=min_hist_date, max_value=today,
                        disabled=custom_disabled, 
                        key="start_date_input", 
                        on_change=custom_dates_changed_callback
                    )
                    st.date_input(
                        "End Date",
                        value=st.session_state.custom_end_date,
                        min_value=min_hist_date, max_value=today,
                        disabled=custom_disabled, 
                        key="end_date_input",
                        on_change=custom_dates_changed_callback
                    )
                
                st.markdown("---") # Separator inside the expander

                # --- Instrument Filter ---
                # Get all unique instruments from the *entire* history
                all_instruments = sorted(trade_df['Instrument'].unique())
                st.multiselect(
                    "Select Instruments (optional)",
                    options=all_instruments,
                    key="instrument_multiselect", 
                    default=st.session_state.selected_instruments,
                    on_change=sync_instruments_callback # Callback to update state
                )
            
            # --- End of Filter Expander ---


            # --- Apply Filters to Data ---
            # Convert filter dates to UTC-aware datetimes for comparison
            # (since the DataFrame 'Date' column is in UTC)
            start_datetime_utc = pd.to_datetime(st.session_state.filter_start_date).tz_localize('UTC')
            # Add one day to the end date to make the range inclusive
            end_datetime_utc = pd.to_datetime(st.session_state.filter_end_date + timedelta(days=1)).tz_localize('UTC')
            
            # Apply date filter
            df_filtered_utc = trade_df[(trade_df['Date'] >= start_datetime_utc) & (trade_df['Date'] < end_datetime_utc)]
            
            # Apply instrument filter if any are selected
            if st.session_state.selected_instruments:
                df_filtered_utc = df_filtered_utc[df_filtered_utc['Instrument'].isin(st.session_state.selected_instruments)].copy()
            else:
                df_filtered_utc = df_filtered_utc.copy()


            # --- Process and Display Filtered Results ---
            if df_filtered_utc.empty:
                st.warning("No trade data found matching your filters.")
            else:
                # --- Convert Timezone for Display (for trade history) ---
                # We keep the UTC dataframe for calculations but convert this
                # one for display in the table.
                try:
                    df_filtered = df_filtered_utc.copy()
                    # Convert to 'Asia/Singapore' for display
                    df_filtered['Date'] = df_filtered['Date'].dt.tz_convert('Asia/Singapore')
                except Exception as tz_error:
                    st.error(f"Error converting timezone: {tz_error}")
                    df_filtered = df_filtered_utc # Fallback to UTC

                # --- Calculate Statistics & Prepare Chart Data ---
                
                # Create a chronologically sorted DF for cumulative charts
                df_filtered_sorted_for_charts = df_filtered_utc.sort_values(by='Date', ascending=True).copy()
                # Calculate Cumulative P/L on the sorted data
                df_filtered_sorted_for_charts['Cumulative P/L'] = df_filtered_sorted_for_charts['Profit/Loss'].cumsum()
                
                # Calculate all key performance indicators
                stats = calculate_statistics(df_filtered, df_filtered_sorted_for_charts)
                
                # Prepare data for Bar Charts (using the display-timezone DF)
                df_filtered['Year'] = df_filtered['Date'].dt.year.astype(str)
                pl_by_year = df_filtered.groupby('Year')['Profit/Loss'].sum().reset_index()
                
                df_filtered['YearMonth'] = df_filtered['Date'].dt.strftime('%Y-%m')
                pl_by_month = df_filtered.groupby('YearMonth')['Profit/Loss'].sum().reset_index()
                
                df_filtered['Day'] = df_filtered['Date'].dt.day_name()
                day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                pl_by_day = df_filtered.groupby('Day')['Profit/Loss'].sum().reindex(day_order).reset_index()
                
                pl_by_instrument = df_filtered.groupby('Instrument')['Profit/Loss'].sum().reset_index()
                count_by_instrument = df_filtered['Instrument'].value_counts().reset_index()
                count_by_instrument.columns = ['Instrument', 'Count']

                # --- Display Primary Statistics with Tooltips ---
                # Check if any filters are active
                is_filtered = (st.session_state.filter_start_date != min_hist_date) or \
                                  (st.session_state.filter_end_date != today) or \
                                  bool(st.session_state.selected_instruments)
                stats_title = "Overall Statistics (Filtered)" if is_filtered else "Overall Statistics"
                st.header(stats_title)
                
                # Display key stats in 3 rows of 3 columns
                cols_row1 = st.columns(3); cols_row2 = st.columns(3); cols_row3 = st.columns(3)
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
                st.header("Visualizations"); st.markdown("---")
                
                # --- Account Balance Chart ---
                st.subheader("Account Balance Trend (After Trade)")
                st.session_state.show_balance_markers = st.toggle("Show Markers", value=st.session_state.show_balance_markers, key="balance_markers_toggle")
                # Filter out trades where balance data was not available (NA)
                balance_data_df = df_filtered_sorted_for_charts.dropna(subset=['Account Balance'])
                
                if not balance_data_df.empty:
                    # Calculate axis ranges with padding
                    min_bal = balance_data_df['Account Balance'].min(); max_bal = balance_data_df['Account Balance'].max(); padding_y = (max_bal - min_bal) * 0.1; yaxis_range_bal = [min_bal - padding_y, max_bal + padding_y]
                    min_date_bal = balance_data_df['Date'].min(); max_date_bal = balance_data_df['Date'].max(); padding_x = timedelta(days=5); xaxis_range_bal = [min_date_bal - padding_x, max_date_bal + padding_x]
                    # Create line chart
                    fig_balance = px.line(balance_data_df, x='Date', y='Account Balance', title="Account Balance After Each Closed Trade", labels={'Account Balance': 'Account Balance (SGD)'}, markers=st.session_state.show_balance_markers)
                    fig_balance.update_traces(hovertemplate='Date: %{x}<br>Balance: $%{y:,.2f}')
                    fig_balance.update_layout(hovermode="x unified", yaxis_range=yaxis_range_bal, xaxis_range=xaxis_range_bal)
                    st.plotly_chart(fig_balance, width='stretch')
                else:
                    st.info("Account balance data not available in transaction history for this period.")
                
                # --- Cumulative P/L Chart ---
                st.markdown("---") 
                st.subheader("Cumulative P/L Trend")
                st.session_state.show_pl_markers = st.toggle("Show Markers", value=st.session_state.show_pl_markers, key="pl_markers_toggle")
                # Calculate axis ranges with padding
                pl_data = df_filtered_sorted_for_charts['Cumulative P/L']; min_pl = pl_data.min(); max_pl = pl_data.max(); padding_y = max(abs(max_pl - min_pl) * 0.1, 1); yaxis_range_pl = [min_pl - padding_y, max_pl + padding_y]
                min_date_pl = df_filtered_sorted_for_charts['Date'].min(); max_date_pl = df_filtered_sorted_for_charts['Date'].max(); padding_x = timedelta(days=5); xaxis_range_pl = [min_date_pl - padding_x, max_date_pl + padding_x]
                # Create line chart
                fig_line = px.line(df_filtered_sorted_for_charts, x='Date', y='Cumulative P/L', labels={'Cumulative P/L': 'Cumulative P/L (SGD)'}, markers=st.session_state.show_pl_markers)
                fig_line.update_traces(hovertemplate='Date: %{x}<br>Cumulative P/L: $%{y:,.2f}')
                fig_line.update_layout(hovermode="x unified", yaxis_range=yaxis_range_pl, xaxis_range=xaxis_range_pl)
                st.plotly_chart(fig_line, width='stretch')
                
                # --- Distribution Charts ---
                st.markdown("---")
                st.subheader("Performance Distribution")
                col1, col2 = st.columns(2)
                with col1:
                    # Pie chart for Win/Loss count
                    pie_data = pd.DataFrame({'Metric': ['Wins', 'Losses'], 'Count': [stats['win_count'], stats['loss_count']]})
                    fig_pie = px.pie(pie_data, values='Count', names='Metric', title="Win/Loss Distribution", color='Metric', color_discrete_map={'Wins': 'green', 'Losses': 'red'})
                    fig_pie.update_traces(textinfo='percent+label+value') 
                    st.plotly_chart(fig_pie, width='stretch')
                with col2:
                    # Histogram for P/L value distribution
                    fig_hist = px.histogram(df_filtered, x="Profit/Loss", nbins=30, title="Distribution of Trade P/L", text_auto=True) 
                    fig_hist.update_traces(marker_line_color='black', marker_line_width=1, hovertemplate='P/L Range: %{x}<br>Count: %{y}') 
                    st.plotly_chart(fig_hist, width='stretch')
                
                # --- Instrument Charts ---
                st.markdown("---")
                st.subheader("Instrument Analysis")
                col1, col2 = st.columns(2) 
                with col1:
                        # Bar chart for P/L by Instrument
                        fig_inst_pl = px.bar(pl_by_instrument.sort_values('Profit/Loss', ascending=False), 
                                             x='Instrument', y='Profit/Loss', color='Profit/Loss', 
                                             color_continuous_scale=px.colors.diverging.RdYlGn, # Red-Yellow-Green scale
                                             title="Total P/L by Instrument")
                        fig_inst_pl.update_traces(hovertemplate='Instrument: %{x}<br>Total P/L: $%{y:,.2f}')
                        st.plotly_chart(fig_inst_pl, width='stretch')
                with col2:
                        # Bar chart for Trade Count by Instrument
                        fig_inst_count = px.bar(count_by_instrument.sort_values('Count', ascending=False), 
                                                x='Instrument', y='Count', title="Trade Count by Instrument")
                        fig_inst_count.update_traces(hovertemplate='Instrument: %{x}<br>Count: %{y}')
                        st.plotly_chart(fig_inst_count, width='stretch')
                
                # --- Time-based Charts ---
                st.markdown("---")
                st.subheader("Performance Over Time")
                # Bar chart for P/L by Year
                fig_yearly_pl = px.bar(pl_by_year, x='Year', y='Profit/Loss', title="Total P/L by Year", 
                                       color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn)
                fig_yearly_pl.update_traces(hovertemplate='Year: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_yearly_pl, width='stretch')
                # Bar chart for P/L by Month
                fig_monthly_pl = px.bar(pl_by_month, x='YearMonth', y='Profit/Loss', title="Total P/L by Month", 
                                        color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, 
                                        labels={'YearMonth': 'Month'})
                fig_monthly_pl.update_traces(hovertemplate='Month: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_monthly_pl, width='stretch')
                # Bar chart for P/L by Day of Week
                st.subheader("Performance by Day of Week", help="This chart shows the total Profit/Loss realized on each day of the week, based on the closing time of the trade in your local timezone (SGT).")
                fig_day_pl = px.bar(pl_by_day, x='Day', y='Profit/Loss', title="Total P/L by Day", 
                                    color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, 
                                    labels={'Day': 'Day'})
                fig_day_pl.update_traces(hovertemplate='Day: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_day_pl, width='stretch')
                st.markdown("---")

                # --- Filtered Trade History Table & Download ---
                st.header("Filtered Trade History")
                # Define columns to show in the table
                columns_to_show = ["Date", "Day", "Instrument", "Buy/Sell", "Amount", "Profit/Loss", "Account Balance"]
                # Ensure all columns exist in the dataframe (e.g. 'Account Balance' might be all NA)
                available_columns = [col for col in columns_to_show if col in df_filtered.columns]
                
                # Prepare CSV for download
                df_csv = df_filtered[available_columns].copy()
                csv_string = df_csv.to_csv(index=False).encode('utf-8')
                
                # Prepare DataFrame for display (format date string)
                df_display = df_filtered[available_columns].copy()
                df_display['Date'] = df_display['Date'].dt.strftime('%d/%m/%Y %H:%M:%S %Z')
                
                # Display table with number formatting
                st.dataframe(df_display.style.format({"Profit/Loss": "{:.2f}", "Account Balance": "{:.2f}"}), width='stretch')
                
                # Download Button
                st.download_button(
                    label="📥 Download Filtered Data as CSV",
                    data=csv_string,
                    file_name=f"oanda_trades_{st.session_state.filter_start_date}_to_{st.session_state.filter_end_date}.csv",
                    mime='text/csv',
                )

        # --- Handle Case: No Trade Data Found ---
        else:
            # This shows if the API fetch worked but returned no trades
            st.warning("No completed trades with P/L found in your account history.")

    # --- Error Handling ---
    except (FileNotFoundError, ValueError) as e:
        # This catches if the *active* config file is deleted or invalid
        st.error(f"Error loading config for {st.session_state.active_environment} account: {e}")
        st.info("Click 'Edit Credentials' in the sidebar to fix or create the configuration.")
        st.stop()
    
    except Exception as e:
        # Catch-all for any other unexpected errors during execution
        st.error(f"An unexpected error occurred: {e}")
        st.exception(e) # Print the full traceback


# --- Callback functions (Defined outside main() for clarity and scope) ---

def preset_changed_callback(min_hist_date, today):
    """
    Callback triggered when the Date Range selectbox (e.g., "YTD", "Custom") changes.
    It updates the session_state filter dates based on the new preset.
    """
    preset = st.session_state.date_preset_radio 
    st.session_state.date_preset = preset 
    
    if preset != "Custom":
        # Calculate the dates for the chosen preset
        start_dt, end_dt = calculate_preset_dates(preset, min_hist_date, today)
        # Update the main filter dates
        st.session_state.filter_start_date = start_dt
        st.session_state.filter_end_date = end_dt
        # Also update the 'custom' dates so they match if the user switches back
        st.session_state.custom_start_date = start_dt
        st.session_state.custom_end_date = end_dt
    else:
        # If "Custom" is selected, use the dates stored in the 'custom' state
        st.session_state.filter_start_date = st.session_state.custom_start_date
        st.session_state.filter_end_date = st.session_state.custom_end_date

def custom_dates_changed_callback():
    """
    Callback triggered when the 'Start Date' or 'End Date' date_input widgets change.
    It updates the session_state filter dates and sets the preset to "Custom".
    """
    # Sync the main filter dates with the custom input widgets
    st.session_state.custom_start_date = st.session_state.start_date_input
    st.session_state.custom_end_date = st.session_state.end_date_input
    st.session_state.filter_start_date = st.session_state.custom_start_date
    st.session_state.filter_end_date = st.session_state.custom_end_date
    # Force the preset to "Custom"
    st.session_state.date_preset = "Custom"

def sync_instruments_callback():
    """
    Callback triggered when the instrument multiselect widget changes.
    It updates the session_state list of selected instruments.
    """
    st.session_state.selected_instruments = st.session_state.instrument_multiselect

# --- Run the main function when the script is executed ---
if __name__ == "__main__":
    main()
