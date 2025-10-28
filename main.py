import configparser
import requests  # <-- We use requests now
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import plotly.express as px
import streamlit as st
from datetime import datetime, timedelta

# --- Configuration (No change) ---

def get_config():
    """
    Reads the configuration file (config.ini) to get API credentials.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    if 'OANDA' not in config:
        raise ValueError("Config file 'config.ini' not found or 'OANDA' section is missing.")
        
    return config['OANDA']

# --- Data Fetching (NEW: Uses 'requests') ---

@st.cache_data
def get_account_summary(refresh_key):
    """
    Connects to Oanda and fetches the basic account summary.
    This cache will bust when 'refresh_key' changes.
    """
    print(f"RUNNING: get_account_summary() with key: {refresh_key}")
    try:
        config = get_config() 
        account_id = config['ACCOUNT_ID']
        access_token = config['ACCESS_TOKEN']
        environment = config['ENVIRONMENT']
        
        base_url = "https://api-fxtrade.oanda.com" if environment == 'live' else "https://api-fxpractice.oanda.com"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        
        summary_url = f"{base_url}/v3/accounts/{account_id}/summary"
        summary_response = requests.get(summary_url, headers=headers)
        summary_response.raise_for_status() # Check for API errors
        return summary_response.json()
        
    except Exception as e:
        st.error(f"Error fetching account summary: {e}")
        return None

@st.cache_data
def fetch_trade_history(refresh_key, last_transaction_id):
    """
    Fetches all transactions from ID 1 up to the last_transaction_id
    using pagination to get ALL records. Includes account balance if available.
    """
    print(f"RUNNING: fetch_trade_history() with key: {refresh_key}, up to ID: {last_transaction_id}")

    config = get_config()
    account_id = config['ACCOUNT_ID']
    access_token = config['ACCESS_TOKEN']
    environment = config['ENVIRONMENT']

    base_url = "https://api-fxtrade.oanda.com" if environment == 'live' else "https://api-fxpractice.oanda.com"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    all_transactions = []
    current_from_id = 1
    page_size = 1000
    true_last_id = int(last_transaction_id)

    print("\n--- Fetching transactions in chunks... ---")
    while current_from_id <= true_last_id:
        current_to_id = min(current_from_id + page_size - 1, true_last_id)
        print(f"Fetching chunk: IDs {current_from_id} to {current_to_id}...")
        transactions_url = f"{base_url}/v3/accounts/{account_id}/transactions/idrange"
        params = {"from": str(current_from_id), "to": str(current_to_id)}
        response = requests.get(transactions_url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        chunk_transactions = data.get('transactions', [])
        if not chunk_transactions: break
        all_transactions.extend(chunk_transactions)
        current_from_id = current_to_id + 1
    print(f"SUCCESS! Fetched a total of {len(all_transactions)} transactions.")

    trade_data = []
    # --- NEW: Process transactions including balance ---
    for t in all_transactions:
        # We only want transactions that represent a closed trade's P/L
        # Typically ORDER_FILL transactions related to closing positions/trades might have 'pl'
        # Let's also check for specific types if needed, but 'pl' is usually sufficient
        if 'pl' in t and float(t['pl']) != 0:
            trade_type = 'Buy' if float(t.get('units', 0)) < 0 else 'Sell' # Use .get for safety

            # Get account balance AFTER the transaction, default to NaN if not found
            balance_after_trade = t.get('accountBalance', None)
            if balance_after_trade:
                balance_after_trade = float(balance_after_trade)
            else:
                balance_after_trade = pd.NA # Use pandas NA for missing numeric data

            trade_data.append({
                "Date": t['time'],
                "Instrument": t['instrument'],
                "Buy/Sell": trade_type,
                "Amount": abs(float(t.get('units', 0))),
                "Profit/Loss": float(t['pl']),
                "Account Balance": balance_after_trade # <-- Add balance here
            })
    # --- END NEW ---

    if not trade_data:
        print("\nNo completed trades with P/L found in this transaction range.")
        return None

    df = pd.DataFrame(trade_data)
    df['Date'] = pd.to_datetime(df['Date'])
    df['Profit/Loss'] = df['Profit/Loss'].astype(float)
    # Convert balance, handling potential NA values
    df['Account Balance'] = pd.to_numeric(df['Account Balance'], errors='coerce')

    df = df.sort_values(by='Date', ascending=False)
    return df

# --- Data Processing ---

def calculate_statistics(df):
    """
    Calculates key performance statistics from the DataFrame.
    """
    stats = {}

    # Basic Counts & P/L
    stats['total_pl'] = df['Profit/Loss'].sum()
    wins_df = df[df['Profit/Loss'] > 0]
    losses_df = df[df['Profit/Loss'] < 0]
    stats['win_count'] = len(wins_df)
    stats['loss_count'] = len(losses_df)
    stats['total_trades'] = stats['win_count'] + stats['loss_count']

    # Win Rate
    if stats['total_trades'] > 0:
        stats['win_rate'] = (stats['win_count'] / stats['total_trades']) * 100
    else:
        stats['win_rate'] = 0

    # Averages
    stats['avg_win'] = wins_df['Profit/Loss'].mean() if stats['win_count'] > 0 else 0
    stats['avg_loss'] = losses_df['Profit/Loss'].mean() if stats['loss_count'] > 0 else 0

    # Most Traded
    stats['most_traded'] = df['Instrument'].mode()[0] if not df.empty else "N/A"

    # Profit Factor & Win/Loss Ratio
    gross_profit = wins_df['Profit/Loss'].sum()
    gross_loss = abs(losses_df['Profit/Loss'].sum())
    stats['profit_factor'] = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0)
    stats['win_loss_ratio'] = (stats['win_count'] / stats['loss_count']) if stats['loss_count'] > 0 else (float('inf') if stats['win_count'] > 0 else 0)

    # --- NEW: Largest Win/Loss ---
    stats['largest_win'] = wins_df['Profit/Loss'].max() if stats['win_count'] > 0 else 0
    stats['largest_loss'] = losses_df['Profit/Loss'].min() if stats['loss_count'] > 0 else 0
    # --- END NEW ---

    return stats

# --- Main App Logic ---

def main():
    st.set_page_config(
        page_title="Oanda Trading Dashboard",
        layout="wide"
    )

    st.title("My Oanda Trading Dashboard 📈")

    # --- 1. REFRESH LOGIC & Initialize Session State ---
    if "refresh_key" not in st.session_state: st.session_state.refresh_key = datetime.now()
    if "selected_instruments" not in st.session_state: st.session_state.selected_instruments = []
    if "show_balance_markers" not in st.session_state: st.session_state.show_balance_markers = False
    if "show_pl_markers" not in st.session_state: st.session_state.show_pl_markers = False
    # --- NEW: Initialize date states ---
    if "start_date" not in st.session_state: st.session_state.start_date = None # Will be set after fetching data
    if "end_date" not in st.session_state: st.session_state.end_date = datetime.now().date() # Default end to today
    if "date_preset" not in st.session_state: st.session_state.date_preset = "All Time" # Default preset


    st.sidebar.header("Data Control")
    if st.sidebar.button("Refresh Live Data"):
        st.session_state.refresh_key = datetime.now()
        st.session_state.selected_instruments = []
        st.session_state.show_balance_markers = False
        st.session_state.show_pl_markers = False
        # Reset date filters on full refresh
        st.session_state.start_date = None
        st.session_state.end_date = datetime.now().date()
        st.session_state.date_preset = "All Time"
        st.rerun()

    refresh_key = st.session_state.refresh_key
    # --- END REFRESH LOGIC ---

    try:
        config = get_config()

        # --- 2. Get Account Summary ---
        summary_response = get_account_summary(refresh_key)
        if summary_response is None: st.stop()
        last_id = summary_response['account']['lastTransactionID']
        account_balance = float(summary_response['account']['balance'])
        account_pl = float(summary_response['account']['pl'])
        margin_avail = float(summary_response['account']['marginAvailable'])

        # --- 3. Display Account Header ---
        st.header(f"Account Summary ({config['ACCOUNT_ID']})")
        st.sidebar.info(f"Last Transaction ID: {last_id}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Account Balance (SGD)", f"${account_balance:,.2f}")
        col2.metric("Unrealized P/L (SGD)", f"${account_pl:,.2f}")
        col3.metric("Margin Available (SGD)", f"${margin_avail:,.2f}")

        # --- 4. Fetch and Process Trade Data ---
        trade_df = fetch_trade_history(refresh_key, last_id)

        if trade_df is not None and not trade_df.empty:

            # --- 5. SIDEBAR FILTERS ---
            st.sidebar.header("Filters")

            # Date Range Calculation
            min_hist_date = trade_df['Date'].min().date()
            max_hist_date = trade_df['Date'].max().date() # Use max date from data for consistency
            today = datetime.now().date()

            # Set initial start date if not already set
            if st.session_state.start_date is None:
                st.session_state.start_date = min_hist_date

            # Date Presets Radio Buttons
            date_options = ["All Time", "Year-to-Date (YTD)", "Last Quarter", "Last Month", "Last 7 Days", "Custom"]
            st.session_state.date_preset = st.sidebar.radio(
                "Select Date Range",
                options=date_options,
                key="date_preset_radio", # Assign key to track selection
                index=date_options.index(st.session_state.date_preset) # Keep selection sticky
            )

            # Update start/end dates based on preset selection
            start_dt = st.session_state.start_date
            end_dt = st.session_state.end_date

            if st.session_state.date_preset == "All Time":
                start_dt = min_hist_date
                end_dt = today
            elif st.session_state.date_preset == "Year-to-Date (YTD)":
                start_dt = datetime(today.year, 1, 1).date()
                end_dt = today
            elif st.session_state.date_preset == "Last Month":
                first_day_current_month = today.replace(day=1)
                last_day_last_month = first_day_current_month - timedelta(days=1)
                first_day_last_month = last_day_last_month.replace(day=1)
                start_dt = first_day_last_month
                end_dt = last_day_last_month
            elif st.session_state.date_preset == "Last 7 Days":
                start_dt = today - timedelta(days=6) # Include today
                end_dt = today
            # Placeholder for Last Quarter - needs more complex date logic
            elif st.session_state.date_preset == "Last Quarter":
                 st.sidebar.warning("Last Quarter preset coming soon!") # Placeholder
                 # If you want to implement this: find current quarter, calc previous quarter start/end
                 start_dt = st.session_state.start_date # Keep custom dates for now
                 end_dt = st.session_state.end_date

            # Update session state if presets changed the dates
            st.session_state.start_date = start_dt
            st.session_state.end_date = end_dt


            # Custom Date Inputs (only enabled if 'Custom' is selected)
            custom_disabled = st.session_state.date_preset != "Custom"
            new_start_date = st.sidebar.date_input(
                "Start Date",
                value=st.session_state.start_date,
                min_value=min_hist_date,
                max_value=today, # Can't select future
                disabled=custom_disabled,
                key="start_date_input"
            )
            new_end_date = st.sidebar.date_input(
                "End Date",
                value=st.session_state.end_date,
                min_value=min_hist_date,
                max_value=today,
                disabled=custom_disabled,
                key="end_date_input"
            )

            # If Custom is selected AND dates change, update state and mark as Custom
            if not custom_disabled and (new_start_date != st.session_state.start_date or new_end_date != st.session_state.end_date):
                st.session_state.start_date = new_start_date
                st.session_state.end_date = new_end_date
                st.session_state.date_preset = "Custom" # Mark as custom if dates are manually changed
                st.rerun() # Rerun to apply changes immediately


            # Instrument Filter
            all_instruments = sorted(trade_df['Instrument'].unique())
            current_selection = st.sidebar.multiselect("Select Instruments (optional)", options=all_instruments, default=st.session_state.selected_instruments)
            if current_selection != st.session_state.selected_instruments:
                 st.session_state.selected_instruments = current_selection
                 st.rerun()

            # --- 6. APPLY FILTERS ---
            # Ensure correct types for comparison
            start_datetime_utc = pd.to_datetime(st.session_state.start_date).tz_localize('UTC')
            # Add time component to end date for inclusive filtering
            end_datetime_utc = pd.to_datetime(st.session_state.end_date + timedelta(days=1)).tz_localize('UTC')

            df_filtered_utc = trade_df[
                (trade_df['Date'] >= start_datetime_utc) &
                (trade_df['Date'] < end_datetime_utc) # Use less than next day's start
            ]
            if st.session_state.selected_instruments:
                 df_filtered_utc = df_filtered_utc[df_filtered_utc['Instrument'].isin(st.session_state.selected_instruments)].copy()
            else:
                 df_filtered_utc = df_filtered_utc.copy()

            # --- 7. Check if Filtered Data Exists ---
            if df_filtered_utc.empty:
                st.warning("No trade data found matching your filters.")
            else:
                # --- Convert Timezone for Display ---
                try:
                    df_filtered = df_filtered_utc.copy()
                    df_filtered['Date'] = df_filtered['Date'].dt.tz_convert('Asia/Singapore')
                except Exception as tz_error: st.error(f"Error converting timezone: {tz_error}"); df_filtered = df_filtered_utc

                # --- 8. Calculate Stats & Prepare Chart Data ---
                stats = calculate_statistics(df_filtered)
                df_filtered_sorted_for_charts = df_filtered_utc.sort_values(by='Date', ascending=True).copy()
                df_filtered_sorted_for_charts['Cumulative P/L'] = df_filtered_sorted_for_charts['Profit/Loss'].cumsum()
                df_filtered['DayOfWeek'] = df_filtered['Date'].dt.day_name()
                day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                pl_by_day = df_filtered.groupby('DayOfWeek')['Profit/Loss'].sum().reindex(day_order).reset_index()
                pl_by_instrument = df_filtered.groupby('Instrument')['Profit/Loss'].sum().reset_index()
                count_by_instrument = df_filtered['Instrument'].value_counts().reset_index()
                count_by_instrument.columns = ['Instrument', 'Count']

                # --- 9. Display Primary Statistics ---
                is_filtered = (st.session_state.start_date != min_hist_date) or \
                              (st.session_state.end_date != today) or \
                              bool(st.session_state.selected_instruments)
                stats_title = "Overall Statistics (Filtered)" if is_filtered else "Overall Statistics"
                st.header(stats_title)
                # (Stats display remains the same)
                cols_row1 = st.columns(4); cols_row2 = st.columns(4)
                cols_row1[0].metric("Total Realized P/L (SGD)", f"${stats['total_pl']:,.2f}")
                cols_row1[1].metric("Total Closed Trades", stats['total_trades'])
                cols_row1[2].metric("Win Rate", f"{stats['win_rate']:.2f}%")
                cols_row1[3].metric("Avg Win / Avg Loss", f"${stats['avg_win']:,.2f} / ${stats['avg_loss']:,.2f}")
                cols_row2[0].metric("Profit Factor", f"{stats['profit_factor']:.2f}")
                cols_row2[1].metric("Win/Loss Ratio", f"{stats['win_loss_ratio']:.2f}")
                cols_row2[2].metric("Largest Win (SGD)", f"${stats['largest_win']:,.2f}")
                cols_row2[3].metric("Largest Loss (SGD)", f"${stats['largest_loss']:,.2f}")

                # --- 10. Charts Section ---
                st.header("Visualizations"); st.markdown("---")
                # (All chart code remains the same as previous version)
                # --- Account Balance Chart ---
                st.subheader("Account Balance Trend (After Trade)")
                st.session_state.show_balance_markers = st.toggle("Show Markers", value=st.session_state.show_balance_markers, key="balance_markers_toggle")
                balance_data_df = df_filtered_sorted_for_charts.dropna(subset=['Account Balance'])
                if not balance_data_df.empty:
                    min_bal = balance_data_df['Account Balance'].min(); max_bal = balance_data_df['Account Balance'].max()
                    padding_y = (max_bal - min_bal) * 0.1; yaxis_range_bal = [min_bal - padding_y, max_bal + padding_y]
                    min_date_bal = balance_data_df['Date'].min(); max_date_bal = balance_data_df['Date'].max()
                    padding_x = timedelta(days=5); xaxis_range_bal = [min_date_bal - padding_x, max_date_bal + padding_x]
                    fig_balance = px.line(balance_data_df, x='Date', y='Account Balance', title="Account Balance After Each Closed Trade", labels={'Account Balance': 'Account Balance (SGD)'}, markers=st.session_state.show_balance_markers)
                    fig_balance.update_traces(hovertemplate='Date: %{x}<br>Balance: $%{y:,.2f}')
                    fig_balance.update_layout(hovermode="x unified", yaxis_range=yaxis_range_bal, xaxis_range=xaxis_range_bal)
                    st.plotly_chart(fig_balance)
                else: st.info("Account balance data not available...")
                st.markdown("---")
                # --- Cumulative P/L Chart ---
                st.subheader("Cumulative P/L Trend")
                st.session_state.show_pl_markers = st.toggle("Show Markers", value=st.session_state.show_pl_markers, key="pl_markers_toggle")
                pl_data = df_filtered_sorted_for_charts['Cumulative P/L']
                min_pl = pl_data.min(); max_pl = pl_data.max()
                padding_y = max(abs(max_pl - min_pl) * 0.1, 1); yaxis_range_pl = [min_pl - padding_y, max_pl + padding_y]
                min_date_pl = df_filtered_sorted_for_charts['Date'].min(); max_date_pl = df_filtered_sorted_for_charts['Date'].max()
                padding_x = timedelta(days=5); xaxis_range_pl = [min_date_pl - padding_x, max_date_pl + padding_x]
                fig_line = px.line(df_filtered_sorted_for_charts, x='Date', y='Cumulative P/L', labels={'Cumulative P/L': 'Cumulative P/L (SGD)'}, markers=st.session_state.show_pl_markers)
                fig_line.update_traces(hovertemplate='Date: %{x}<br>Cumulative P/L: $%{y:,.2f}')
                fig_line.update_layout(hovermode="x unified", yaxis_range=yaxis_range_pl, xaxis_range=xaxis_range_pl)
                st.plotly_chart(fig_line)
                st.markdown("---")
                # --- Performance Distribution ---
                st.subheader("Performance Distribution")
                col1, col2 = st.columns(2)
                with col1:
                    pie_data = pd.DataFrame({'Metric': ['Wins', 'Losses'], 'Count': [stats['win_count'], stats['loss_count']]})
                    fig_pie = px.pie(pie_data, values='Count', names='Metric', title="Win/Loss Distribution", color='Metric', color_discrete_map={'Wins': 'green', 'Losses': 'red'})
                    fig_pie.update_traces(textinfo='percent+label+value')
                    st.plotly_chart(fig_pie)
                with col2:
                    fig_hist = px.histogram(df_filtered, x="Profit/Loss", nbins=30, title="Distribution of Trade P/L", text_auto=True)
                    fig_hist.update_traces(marker_line_color='black', marker_line_width=1, hovertemplate='P/L Range: %{x}<br>Count: %{y}')
                    st.plotly_chart(fig_hist)
                st.markdown("---")
                # --- Instrument Analysis ---
                st.subheader("Instrument Analysis")
                col1, col2 = st.columns(2)
                with col1:
                     fig_inst_pl = px.bar(pl_by_instrument.sort_values('Profit/Loss', ascending=False), x='Instrument', y='Profit/Loss', color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, title="Total P/L by Instrument")
                     fig_inst_pl.update_traces(hovertemplate='Instrument: %{x}<br>Total P/L: $%{y:,.2f}')
                     st.plotly_chart(fig_inst_pl)
                with col2:
                     fig_inst_count = px.bar(count_by_instrument.sort_values('Count', ascending=False), x='Instrument', y='Count', title="Trade Count by Instrument")
                     fig_inst_count.update_traces(hovertemplate='Instrument: %{x}<br>Count: %{y}')
                     st.plotly_chart(fig_inst_count)
                st.markdown("---")
                # --- Day of Week ---
                st.subheader("Performance by Day of Week", help="...")
                fig_day_pl = px.bar(pl_by_day, x='DayOfWeek', y='Profit/Loss', title="Total P/L by Day", color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, labels={'DayOfWeek': 'Day'})
                fig_day_pl.update_traces(hovertemplate='Day: %{x}<br>Total P/L: $%{y:,.2f}')
                st.plotly_chart(fig_day_pl)
                st.markdown("---")

                # --- 11. Filtered Trade History ---
                st.header("Filtered Trade History")
                df_display = df_filtered.copy()
                df_display['Date'] = df_display['Date'].dt.strftime('%d/%m/%Y %H:%M:%S %Z')
                st.dataframe(df_display.style.format({"Profit/Loss": "{:.2f}", "Account Balance": "{:.2f}"}), width='stretch')

        else:
            st.warning("No completed trades with P/L found in your account history.")

    except FileNotFoundError: st.error("ERROR: 'config.ini' file not found."); st.info("...")
    except Exception as e: st.error(f"An unexpected error occurred: {e}"); st.exception(e)

if __name__ == "__main__":
    main()