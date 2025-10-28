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
    using pagination to get ALL records.
    """
    print(f"RUNNING: fetch_trade_history() with key: {refresh_key}, up to ID: {last_transaction_id}")
    
    config = get_config()
    account_id = config['ACCOUNT_ID']
    access_token = config['ACCESS_TOKEN']
    environment = config['ENVIRONMENT']

    base_url = "https://api-fxtrade.oanda.com" if environment == 'live' else "https://api-fxpractice.oanda.com"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # --- NEW: Pagination Logic ---
    all_transactions = []
    current_from_id = 1
    page_size = 1000  # We know this is the limit
    true_last_id = int(last_transaction_id) # Convert to int

    print("\n--- Fetching transactions in chunks... ---")

    while current_from_id <= true_last_id:
        current_to_id = min(current_from_id + page_size - 1, true_last_id)
        print(f"Fetching chunk: IDs {current_from_id} to {current_to_id}...")
        
        transactions_url = f"{base_url}/v3/accounts/{account_id}/transactions/idrange"
        params = {"from": str(current_from_id), "to": str(current_to_id)}
        
        response = requests.get(transactions_url, headers=headers, params=params)
        response.raise_for_status() # Check for API errors
        data = response.json()
        
        chunk_transactions = data.get('transactions', [])
        if not chunk_transactions:
            break # Stop if we get an empty list

        all_transactions.extend(chunk_transactions)
        current_from_id = current_to_id + 1
    
    print(f"SUCCESS! Fetched a total of {len(all_transactions)} transactions.")
    # --- END: Pagination Logic ---

    # --- OLD: Processing Logic (This part is good) ---
    trade_data = []
    
    for t in all_transactions: # Use the new all_transactions list
        if 'pl' in t and float(t['pl']) != 0:
            trade_type = 'Buy' if float(t['units']) < 0 else 'Sell'
            
            trade_data.append({
                "Date": t['time'],
                "Instrument": t['instrument'],
                "Buy/Sell": trade_type,
                "Amount": abs(float(t['units'])),
                "Profit/Loss": float(t['pl'])
            })
            
    if not trade_data:
        print("\nNo completed trades with P/L found in this transaction range.")
        return None

    df = pd.DataFrame(trade_data)
    df['Date'] = pd.to_datetime(df['Date'])
    df['Profit/Loss'] = df['Profit/Loss'].astype(float)
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

    # --- 1. REFRESH LOGIC ---
    if "refresh_key" not in st.session_state:
        st.session_state.refresh_key = datetime.now()
    if "selected_instruments" not in st.session_state:
        st.session_state.selected_instruments = []

    st.sidebar.header("Data Control")
    if st.sidebar.button("Refresh Live Data"):
        st.session_state.refresh_key = datetime.now()
        st.session_state.selected_instruments = []
        st.rerun()

    refresh_key = st.session_state.refresh_key
    # --- END REFRESH LOGIC ---

    try:
        config = get_config()

        # --- 2. Get Account Summary ---
        summary_response = get_account_summary(refresh_key)
        if summary_response is None:
            st.stop()

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

            min_date = trade_df['Date'].min().date()
            max_date = datetime.now().date()
            start_date = st.sidebar.date_input("Select Start Date", value=min_date, min_value=min_date, max_value=max_date)
            start_datetime_utc = pd.to_datetime(start_date).tz_localize('UTC')

            all_instruments = sorted(trade_df['Instrument'].unique())
            current_selection = st.sidebar.multiselect("Select Instruments (optional)", options=all_instruments, default=st.session_state.selected_instruments)
            if current_selection != st.session_state.selected_instruments:
                 st.session_state.selected_instruments = current_selection
                 st.rerun()

            # --- 6. APPLY FILTERS ---
            df_filtered = trade_df[trade_df['Date'] >= start_datetime_utc]
            if st.session_state.selected_instruments:
                 df_filtered = df_filtered[df_filtered['Instrument'].isin(st.session_state.selected_instruments)].copy()
            else:
                 df_filtered = df_filtered.copy()

            # --- 7. Check if Filtered Data Exists ---
            if df_filtered.empty:
                st.warning("No trade data found matching your filters.")
            else:
                # --- 8. Calculate Stats & Prepare Chart Data ---
                stats = calculate_statistics(df_filtered)
                df_filtered_sorted = df_filtered.sort_values(by='Date', ascending=True)
                df_filtered_sorted['Cumulative P/L'] = df_filtered_sorted['Profit/Loss'].cumsum()
                pl_by_instrument = df_filtered.groupby('Instrument')['Profit/Loss'].sum().reset_index()
                count_by_instrument = df_filtered['Instrument'].value_counts().reset_index()
                count_by_instrument.columns = ['Instrument', 'Count']

                # --- NEW: Day of Week Analysis ---
                df_filtered['DayOfWeek'] = df_filtered['Date'].dt.day_name()
                # Ensure correct order of days
                day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                pl_by_day = df_filtered.groupby('DayOfWeek')['Profit/Loss'].sum().reindex(day_order).reset_index()
                # --- END NEW ---

                # --- 9. Display Primary Statistics ---
                is_filtered = False
                if start_date != min_date: is_filtered = True
                if st.session_state.selected_instruments: is_filtered = True
                stats_title = "Overall Statistics (Filtered)" if is_filtered else "Overall Statistics"
                st.header(stats_title)

                # Split stats into two rows for better layout
                cols_row1 = st.columns(4)
                cols_row1[0].metric("Total Realized P/L (SGD)", f"${stats['total_pl']:,.2f}")
                cols_row1[1].metric("Total Closed Trades", stats['total_trades'])
                cols_row1[2].metric("Win Rate", f"{stats['win_rate']:.2f}%")
                cols_row1[3].metric("Avg Win / Avg Loss", f"${stats['avg_win']:,.2f} / ${stats['avg_loss']:,.2f}")

                cols_row2 = st.columns(4)
                cols_row2[0].metric("Profit Factor", f"{stats['profit_factor']:.2f}")
                cols_row2[1].metric("Win/Loss Ratio", f"{stats['win_loss_ratio']:.2f}")
                cols_row2[2].metric("Largest Win (SGD)", f"${stats['largest_win']:,.2f}") # <-- NEW
                cols_row2[3].metric("Largest Loss (SGD)", f"${stats['largest_loss']:,.2f}") # <-- NEW

                # --- 10. Charts Section ---
                st.header("Visualizations")
                st.markdown("---") # Add a horizontal line for separation

                # Row 1: Cumulative P/L
                st.subheader("Cumulative P/L Trend")
                fig_line = px.line(df_filtered_sorted, x='Date', y='Cumulative P/L', labels={'Cumulative P/L': 'Cumulative P/L (SGD)'})
                fig_line.update_layout(hovermode="x unified")
                st.plotly_chart(fig_line, use_container_width=True)

                st.markdown("---") # Add a horizontal line

                # Row 2: Performance Breakdown (Pie) + P/L Distribution (Histogram)
                st.subheader("Performance Distribution")
                col1, col2 = st.columns(2)
                with col1:
                    pie_data = pd.DataFrame({'Metric': ['Wins', 'Losses'], 'Count': [stats['win_count'], stats['loss_count']]})
                    fig_pie = px.pie(pie_data, values='Count', names='Metric', title="Win/Loss Distribution", color='Metric', color_discrete_map={'Wins': 'green', 'Losses': 'red'})
                    fig_pie.update_traces(textinfo='percent+label+value')
                    st.plotly_chart(fig_pie, use_container_width=True)
                with col2:
                    fig_hist = px.histogram(df_filtered, x="Profit/Loss", nbins=30, title="Distribution of Trade P/L", text_auto=True)
                    fig_hist.update_traces(marker_line_color='black', marker_line_width=1)
                    st.plotly_chart(fig_hist, use_container_width=True)

                st.markdown("---") # Add a horizontal line

                # Row 3: Instrument Analysis
                st.subheader("Instrument Analysis")
                col1, col2 = st.columns(2)
                with col1:
                     fig_inst_pl = px.bar(pl_by_instrument.sort_values('Profit/Loss', ascending=False), x='Instrument', y='Profit/Loss', color='Profit/Loss', color_continuous_scale=px.colors.diverging.RdYlGn, title="Total P/L by Instrument")
                     st.plotly_chart(fig_inst_pl, use_container_width=True)
                with col2:
                     fig_inst_count = px.bar(count_by_instrument.sort_values('Count', ascending=False), x='Instrument', y='Count', title="Trade Count by Instrument")
                     st.plotly_chart(fig_inst_count, use_container_width=True)

                st.markdown("---") # Add a horizontal line

                # --- NEW: Row 4: Day of Week Analysis ---
                st.subheader("Performance by Day of Week")
                fig_day_pl = px.bar(
                    pl_by_day,
                    x='Day',
                    y='Profit/Loss',
                    title="Total P/L by Day of Week",
                    color='Profit/Loss',
                    color_continuous_scale=px.colors.diverging.RdYlGn # Same color scale
                )
                st.plotly_chart(fig_day_pl, use_container_width=True)
                # --- END NEW ---

                # --- 11. Filtered Trade History ---
                st.header("Filtered Trade History")
                st.dataframe(df_filtered.style.format({"Profit/Loss": "{:.2f}"}), use_container_width=True)

        else:
            st.warning("No completed trades with P/L found in your account history.")

    except FileNotFoundError:
        st.error("ERROR: 'config.ini' file not found.")
        st.info("Please copy 'config.ini.template' to 'config.ini' and fill in your Oanda credentials.")
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        st.exception(e)

if __name__ == "__main__":
    main()