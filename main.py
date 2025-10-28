# --- Imports ---
import configparser         # For reading the configuration file (API keys)
import requests             # For making HTTP requests to the Oanda API
import pandas as pd         # For data manipulation and analysis (DataFrames)
import plotly.express as px # For creating interactive charts
import streamlit as st      # For creating the web application interface
from datetime import datetime, timedelta # For handling dates and times

# --- Configuration Loading ---

def get_config():
    """
    Reads API credentials and settings from the 'config.ini' file.
    Raises an error if the file or the 'OANDA' section is missing.
    """
    config = configparser.ConfigParser()
    config.read('config.ini') # Load the config file

    if 'OANDA' not in config:
        # Error handling if config is invalid
        raise ValueError("Config file 'config.ini' not found or 'OANDA' section is missing.")

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
        # This indicates a closed trade or position adjustment with realized P/L.
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
                "Date": t['time'],                      # Timestamp of the transaction (closing time)
                "Instrument": t['instrument'],          # Trading instrument (e.g., EUR_USD)
                "Buy/Sell": trade_type,                 # Original trade direction (Buy or Sell)
                "Amount": abs(float(t.get('units', 0))),# Size of the closed trade (absolute value)
                "Profit/Loss": float(t['pl']),          # Realized profit or loss for this trade
                "Account Balance": balance_after_trade  # Account balance after this transaction
            })

    if not trade_data:
        # Handle case where no closed trades were found
        print("\nNo completed trades with P/L found in this transaction range.")
        return None # Return None to indicate no data

    # Convert the list of trade data into a pandas DataFrame
    df = pd.DataFrame(trade_data)
    # Convert the 'Date' column from string to timezone-aware datetime objects (UTC initially)
    df['Date'] = pd.to_datetime(df['Date'])
    # Ensure 'Profit/Loss' is a float
    df['Profit/Loss'] = df['Profit/Loss'].astype(float)
    # Convert 'Account Balance' to numeric, setting errors='coerce' turns non-numeric values into NA
    df['Account Balance'] = pd.to_numeric(df['Account Balance'], errors='coerce')

    # Sort the DataFrame by Date in descending order (most recent first) for display later
    df = df.sort_values(by='Date', ascending=False)
    # Return the processed DataFrame
    return df

# --- Data Processing Function ---
def calculate_statistics(df, df_sorted_for_charts):
    """
    Calculates various performance statistics based on the filtered trade data.
    Requires the filtered DataFrame (df) and a chronologically sorted version
    (df_sorted_for_charts) which includes 'Cumulative P/L' for drawdown calculation.
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
    gross_profit = wins_df['Profit/Loss'].sum()         # Sum of all positive P/L
    gross_loss = abs(losses_df['Profit/Loss'].sum())    # Sum of absolute values of negative P/L

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
    # Uses the pre-calculated 'Cumulative P/L' column from the sorted DataFrame
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
        # Set defaults if 'Cumulative P/L' column is missing (should not happen)
        stats['max_drawdown_value'] = 0
        stats['max_drawdown_percent'] = 0

    # Return the dictionary containing all calculated statistics
    return stats

# --- Helper function to calculate preset date ranges ---
def calculate_preset_dates(preset, min_hist_date, today):
    """Calculates the start and end dates based on the selected preset string."""
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
    # Session state persists values between reruns (user interactions)
    # Initialize keys if they don't exist yet to prevent errors on first run
    if "refresh_key" not in st.session_state: st.session_state.refresh_key = datetime.now()
    if "selected_instruments" not in st.session_state: st.session_state.selected_instruments = []
    if "show_balance_markers" not in st.session_state: st.session_state.show_balance_markers = False
    if "show_pl_markers" not in st.session_state: st.session_state.show_pl_markers = False
    # filter_start/end_date store the dates actively used for filtering data
    if "filter_start_date" not in st.session_state: st.session_state.filter_start_date = None
    if "filter_end_date" not in st.session_state: st.session_state.filter_end_date = datetime.now().date()
    # custom_start/end_date store the values from the date input widgets when "Custom" is active
    if "custom_start_date" not in st.session_state: st.session_state.custom_start_date = None
    if "custom_end_date" not in st.session_state: st.session_state.custom_end_date = datetime.now().date()
    # date_preset stores the selection from the radio buttons
    if "date_preset" not in st.session_state: st.session_state.date_preset = "All Time"

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
            # Render the radio button. Its state is automatically managed by Streamlit via its key.
            # 'on_change' calls the specified callback function *after* the internal state is updated.
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
                # Render date inputs. Their state is managed via their keys.
                # 'on_change' calls the callback *after* internal state updates.
                st.sidebar.date_input(
                    "Start Date",
                    value=st.session_state.custom_start_date, # Display the stored custom start date
                    min_value=min_hist_date, max_value=today,
                    disabled=custom_disabled, # Should always be False here, but good practice
                    key="start_date_input", # Unique key for this widget
                    on_change=custom_dates_changed_callback # Function to sync state if changed
                )
                st.sidebar.date_input(
                    "End Date",
                    value=st.session_state.custom_end_date, # Display the stored custom end date
                    min_value=min_hist_date, max_value=today,
                    disabled=custom_disabled, # Should always be False here
                    key="end_date_input", # Unique key
                    on_change=custom_dates_changed_callback # Function to sync state if changed
                )
                st.sidebar.markdown("---") # Separator


            # --- Instrument Filter ---
            all_instruments = sorted(trade_df['Instrument'].unique())
            # Render multiselect. State managed via key and callback.
            st.sidebar.multiselect(
                "Select Instruments (optional)",
                options=all_instruments,
                key="instrument_multiselect", # Unique key
                default=st.session_state.selected_instruments, # Display current selection from state
                on_change=sync_instruments_callback # Function to update state if changed
            )


            # --- Apply Filters to Data ---
            # Use the 'filter_start_date' and 'filter_end_date' from state, which are updated by callbacks.
            start_datetime_utc = pd.to_datetime(st.session_state.filter_start_date).tz_localize('UTC')
            # Add 1 day to end date and use '<' to include all times on the selected end day.
            end_datetime_utc = pd.to_datetime(st.session_state.filter_end_date + timedelta(days=1)).tz_localize('UTC')

            # Filter the main DataFrame based on dates
            df_filtered_utc = trade_df[(trade_df['Date'] >= start_datetime_utc) & (trade_df['Date'] < end_datetime_utc)]
            # Apply instrument filter if any instruments are selected in state
            if st.session_state.selected_instruments:
                df_filtered_utc = df_filtered_utc[df_filtered_utc['Instrument'].isin(st.session_state.selected_instruments)].copy()
            else:
                df_filtered_utc = df_filtered_utc.copy() # Ensure it's a copy even if no instrument filter


            # --- Process and Display Filtered Results ---
            if df_filtered_utc.empty:
                # Show message if no trades match the current filters
                st.warning("No trade data found matching your filters.")
            else:
                # --- Convert Timezone for Display ---
                # Create a copy for display purposes and convert 'Date' column to local time (SGT)
                try:
                    df_filtered = df_filtered_utc.copy()
                    df_filtered['Date'] = df_filtered['Date'].dt.tz_convert('Asia/Singapore')
                except Exception as tz_error:
                    # Fallback to UTC if timezone conversion fails
                    st.error(f"Error converting timezone: {tz_error}")
                    df_filtered = df_filtered_utc

                # --- Calculate Statistics & Prepare Chart Data ---
                # Create a sorted version (by original UTC time) for time-series charts (Balance, Cum P/L)
                df_filtered_sorted_for_charts = df_filtered_utc.sort_values(by='Date', ascending=True).copy()
                # Calculate Cumulative P/L on the sorted data
                df_filtered_sorted_for_charts['Cumulative P/L'] = df_filtered_sorted_for_charts['Profit/Loss'].cumsum()
                # Calculate all statistics (including drawdown using the sorted df)
                stats = calculate_statistics(df_filtered, df_filtered_sorted_for_charts)

                # Prepare data for time-period charts (using local time df)
                df_filtered['Year'] = df_filtered['Date'].dt.year.astype(str)
                pl_by_year = df_filtered.groupby('Year')['Profit/Loss'].sum().reset_index()
                df_filtered['YearMonth'] = df_filtered['Date'].dt.strftime('%Y-%m')
                pl_by_month = df_filtered.groupby('YearMonth')['Profit/Loss'].sum().reset_index()
                df_filtered['DayOfWeek'] = df_filtered['Date'].dt.day_name()
                day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                pl_by_day = df_filtered.groupby('DayOfWeek')['Profit/Loss'].sum().reindex(day_order).reset_index()

                # Prepare data for instrument charts (using local time df)
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
                # Toggle for showing markers on the line chart
                st.session_state.show_balance_markers = st.toggle("Show Markers", value=st.session_state.show_balance_markers, key="balance_markers_toggle")
                # Prepare data (drop rows with missing balance)
                balance_data_df = df_filtered_sorted_for_charts.dropna(subset=['Account Balance'])
                if not balance_data_df.empty:
                    # Calculate fixed axis ranges for stability when toggling markers
                    min_bal = balance_data_df['Account Balance'].min(); max_bal = balance_data_df['Account Balance'].max(); padding_y = (max_bal - min_bal) * 0.1; yaxis_range_bal = [min_bal - padding_y, max_bal + padding_y]
                    min_date_bal = balance_data_df['Date'].min(); max_date_bal = balance_data_df['Date'].max(); padding_x = timedelta(days=5); xaxis_range_bal = [min_date_bal - padding_x, max_date_bal + padding_x]
                    # Create the Plotly line chart
                    fig_balance = px.line(balance_data_df, x='Date', y='Account Balance', title="Account Balance After Each Closed Trade", labels={'Account Balance': 'Account Balance (SGD)'}, markers=st.session_state.show_balance_markers)
                    # Customize hover text format
                    fig_balance.update_traces(hovertemplate='Date: %{x}<br>Balance: $%{y:,.2f}')
                    # Apply fixed ranges and hover mode
                    fig_balance.update_layout(hovermode="x unified", yaxis_range=yaxis_range_bal, xaxis_range=xaxis_range_bal)
                    # Display the chart
                    st.plotly_chart(fig_balance)
                else:
                    # Show message if balance data is missing
                    st.info("Account balance data not available in transaction history for this period.")
                st.markdown("---") # Separator


                # --- Cumulative P/L Chart ---
                st.subheader("Cumulative P/L Trend")
                # Toggle for markers
                st.session_state.show_pl_markers = st.toggle("Show Markers", value=st.session_state.show_pl_markers, key="pl_markers_toggle")
                # Calculate fixed axis ranges
                pl_data = df_filtered_sorted_for_charts['Cumulative P/L']; min_pl = pl_data.min(); max_pl = pl_data.max(); padding_y = max(abs(max_pl - min_pl) * 0.1, 1); yaxis_range_pl = [min_pl - padding_y, max_pl + padding_y]
                min_date_pl = df_filtered_sorted_for_charts['Date'].min(); max_date_pl = df_filtered_sorted_for_charts['Date'].max(); padding_x = timedelta(days=5); xaxis_range_pl = [min_date_pl - padding_x, max_date_pl + padding_x]
                # Create the line chart
                fig_line = px.line(df_filtered_sorted_for_charts, x='Date', y='Cumulative P/L', labels={'Cumulative P/L': 'Cumulative P/L (SGD)'}, markers=st.session_state.show_pl_markers)
                # Customize hover text
                fig_line.update_traces(hovertemplate='Date: %{x}<br>Cumulative P/L: $%{y:,.2f}')
                # Apply fixed ranges and hover mode
                fig_line.update_layout(hovermode="x unified", yaxis_range=yaxis_range_pl, xaxis_range=xaxis_range_pl)
                # Display chart
                st.plotly_chart(fig_line)
                st.markdown("---") # Separator


                # --- Performance Distribution Section ---
                st.subheader("Performance Distribution")
                # Use columns for side-by-side charts
                col1, col2 = st.columns(2)
                with col1:
                    # Win/Loss Pie Chart
                    pie_data = pd.DataFrame({'Metric': ['Wins', 'Losses'], 'Count': [stats['win_count'], stats['loss_count']]})
                    fig_pie = px.pie(pie_data, values='Count', names='Metric', title="Win/Loss Distribution", color='Metric', color_discrete_map={'Wins': 'green', 'Losses': 'red'})
                    fig_pie.update_traces(textinfo='percent+label+value') # Show details on slices
                    st.plotly_chart(fig_pie)
                with col2:
                    # P/L Histogram
                    fig_hist = px.histogram(df_filtered, x="Profit/Loss", nbins=30, title="Distribution of Trade P/L", text_auto=True) # text_auto adds counts on bars
                    fig_hist.update_traces(marker_line_color='black', marker_line_width=1, hovertemplate='P/L Range: %{x}<br>Count: %{y}') # Add outlines and format hover
                    st.plotly_chart(fig_hist)
                st.markdown("---") # Separator


                # --- Instrument Analysis Section ---
                st.subheader("Instrument Analysis")
                col1, col2 = st.columns(2) # Side-by-side layout
                with col1:
                    # P/L by Instrument Bar Chart
                     fig_inst_pl = px.bar(pl_by_instrument.sort_values('Profit/Loss', ascending=False), x='Instrument', y='Profit/Loss', color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, title="Total P/L by Instrument")
                     fig_inst_pl.update_traces(hovertemplate='Instrument: %{x}<br>Total P/L: $%{y:,.2f}')
                     st.plotly_chart(fig_inst_pl)
                with col2:
                    # Trade Count by Instrument Bar Chart
                     fig_inst_count = px.bar(count_by_instrument.sort_values('Count', ascending=False), x='Instrument', y='Count', title="Trade Count by Instrument")
                     fig_inst_count.update_traces(hovertemplate='Instrument: %{x}<br>Count: %{y}')
                     st.plotly_chart(fig_inst_count)
                st.markdown("---") # Separator


                # --- Performance Over Time Section ---
                st.subheader("Performance Over Time")

                # Yearly Performance Bar Chart
                fig_yearly_pl = px.bar(pl_by_year, x='Year', y='Profit/Loss', title="Total P/L by Year", color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn)
                fig_yearly_pl.update_traces(hovertemplate='Year: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_yearly_pl)

                # Monthly Performance Bar Chart
                fig_monthly_pl = px.bar(pl_by_month, x='YearMonth', y='Profit/Loss', title="Total P/L by Month", color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, labels={'YearMonth': 'Month'})
                fig_monthly_pl.update_traces(hovertemplate='Month: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_monthly_pl)

                # Day of Week Performance Bar Chart
                # Subheader with tooltip is placed here, just before the chart
                st.subheader("Performance by Day of Week", help="This chart shows the total Profit/Loss realized on each day of the week, based on the closing time of the trade in your local timezone (SGT). Trades opened on one day but closed after midnight will be attributed to the closing day.")
                fig_day_pl = px.bar(pl_by_day, x='DayOfWeek', y='Profit/Loss', title="Total P/L by Day", color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, labels={'DayOfWeek': 'Day'})
                fig_day_pl.update_traces(hovertemplate='Day: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_day_pl)
                st.markdown("---") # Separator


                # --- Filtered Trade History Table & Download ---
                st.header("Filtered Trade History")
                # Create a copy for display formatting
                df_display = df_filtered.copy()
                # Format the 'Date' column to DD/MM/YYYY HH:MM:SS Timezone (e.g., SGT)
                df_display['Date'] = df_display['Date'].dt.strftime('%d/%m/%Y %H:%M:%S %Z')
                # Display the DataFrame with formatting for P/L and Balance columns
                st.dataframe(df_display.style.format({"Profit/Loss": "{:.2f}", "Account Balance": "{:.2f}"}), width='stretch')

                # Convert the display DataFrame to a CSV string for downloading
                csv_string = df_display.to_csv(index=False).encode('utf-8')
                # Add the download button
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
    except FileNotFoundError:
        # Specific error if config.ini is missing
        st.error("ERROR: 'config.ini' file not found.")
        st.info("Please copy 'config.ini.template' to 'config.ini' and fill in your Oanda credentials.")
    except Exception as e:
        # Catch-all for any other unexpected errors
        st.error(f"An unexpected error occurred: {e}")
        st.exception(e) # Display the full error traceback in the app for debugging


# --- Callback functions (Defined outside main() for clarity and scope) ---

def preset_changed_callback(min_hist_date, today):
    """Callback function executed when the date preset radio button changes."""
    preset = st.session_state.date_preset_radio # Get the new value selected by the user
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
    """Callback function executed when the Start Date or End Date input widget changes."""
    # Update the custom date state variables from the input widget keys
    st.session_state.custom_start_date = st.session_state.start_date_input
    st.session_state.custom_end_date = st.session_state.end_date_input
    # Immediately sync the active filter dates to match the new custom dates
    st.session_state.filter_start_date = st.session_state.custom_start_date
    st.session_state.filter_end_date = st.session_state.custom_end_date
    # Ensure the preset state reflects "Custom" if it wasn't already
    st.session_state.date_preset = "Custom"


def sync_instruments_callback():
    """Callback function executed when the instrument multiselect widget changes."""
    # Update the selected instruments state variable from the multiselect widget key
    st.session_state.selected_instruments = st.session_state.instrument_multiselect

# --- Run the main function when the script is executed ---
if __name__ == "__main__":
    main()