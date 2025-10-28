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
        
    # --- NEW STATS ---
    gross_profit = wins_df['Profit/Loss'].sum()
    gross_loss = abs(losses_df['Profit/Loss'].sum()) # Use absolute value for loss

    # Profit Factor
    if gross_loss > 0:
        stats['profit_factor'] = gross_profit / gross_loss
    elif gross_profit > 0:
        stats['profit_factor'] = float('inf') # Indicate infinite profit factor if no losses
    else:
        stats['profit_factor'] = 0 # No profits or losses

    # Win/Loss Ratio
    if stats['loss_count'] > 0:
        stats['win_loss_ratio'] = stats['win_count'] / stats['loss_count']
    elif stats['win_count'] > 0:
        stats['win_loss_ratio'] = float('inf') # Indicate infinite ratio if no losses
    else:
        stats['win_loss_ratio'] = 0 # No wins or losses
    # --- END NEW STATS ---

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

    st.sidebar.header("Data Control")
    if st.sidebar.button("Refresh Live Data"):
        st.session_state.refresh_key = datetime.now()
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

            # Date Filter
            min_date = trade_df['Date'].min().date()
            max_date = datetime.now().date()
            start_date = st.sidebar.date_input(
                "Select Start Date",
                value=min_date,
                min_value=min_date,
                max_value=max_date
            )
            start_datetime_utc = pd.to_datetime(start_date).tz_localize('UTC')

            # Instrument Filter
            all_instruments = sorted(trade_df['Instrument'].unique())
            selected_instruments = st.sidebar.multiselect(
                "Select Instruments (optional)",
                options=all_instruments,
                default=all_instruments # Default to all selected
            )

            # --- 6. APPLY FILTERS ---
            df_filtered = trade_df[trade_df['Date'] >= start_datetime_utc]
            if selected_instruments: # Only filter if instruments are selected
                 df_filtered = df_filtered[df_filtered['Instrument'].isin(selected_instruments)].copy()
            else: # If nothing selected, show warning but continue with date-filtered data
                 st.sidebar.warning("No instruments selected. Showing data for all instruments in date range.")
                 df_filtered = df_filtered.copy() # Ensure it's a copy

            # --- 7. Check if Filtered Data Exists ---
            if df_filtered.empty:
                st.warning("No trade data found matching your filters.")
            else:
                # --- 8. Calculate Stats & Prepare Chart Data ---
                stats = calculate_statistics(df_filtered)

                # Cumulative P/L Data
                df_filtered_sorted = df_filtered.sort_values(by='Date', ascending=True)
                df_filtered_sorted['Cumulative P/L'] = df_filtered_sorted['Profit/Loss'].cumsum()

                # Instrument P/L Data
                pl_by_instrument = df_filtered.groupby('Instrument')['Profit/Loss'].sum().reset_index()

                # Instrument Count Data
                count_by_instrument = df_filtered['Instrument'].value_counts().reset_index()
                count_by_instrument.columns = ['Instrument', 'Count'] # Rename columns

                # --- 9. Display Primary Statistics ---
                st.header("Overall Statistics (Filtered)")
                cols = st.columns(6) # Now 6 columns for stats
                cols[0].metric("Total Realized P/L (SGD)", f"${stats['total_pl']:,.2f}")
                cols[1].metric("Total Closed Trades", stats['total_trades'])
                cols[2].metric("Win Rate", f"{stats['win_rate']:.2f}%")
                cols[3].metric("Avg Win / Avg Loss", f"${stats['avg_win']:,.2f} / ${stats['avg_loss']:,.2f}")
                cols[4].metric("Profit Factor", f"{stats['profit_factor']:.2f}")
                cols[5].metric("Win/Loss Ratio", f"{stats['win_loss_ratio']:.2f}")


                # --- 10. Charts Section ---
                st.header("Visualizations")

                # Row 1: Cumulative P/L
                fig_line = px.line(
                    df_filtered_sorted, x='Date', y='Cumulative P/L',
                    title="Cumulative P/L Trend", labels={'Cumulative P/L': 'Cumulative P/L (SGD)'}
                )
                fig_line.update_layout(hovermode="x unified")
                st.plotly_chart(fig_line, use_container_width=True)

                # Row 2: Performance Breakdown + P/L Distribution
                col1, col2 = st.columns(2)
                with col1:
                    # Wins vs Losses Bar Chart
                    bar_data = pd.DataFrame({'Metric': ['Wins', 'Losses'], 'Count': [stats['win_count'], stats['loss_count']]})
                    fig_bar = px.bar(
                        bar_data, x='Metric', y='Count', color='Metric',
                        color_discrete_map={'Wins': 'green', 'Losses': 'red'},
                        title="Wins vs. Losses"
                    )
                    fig_bar.update_layout(showlegend=False)
                    st.plotly_chart(fig_bar, use_container_width=True)
                with col2:
                    # P/L Distribution Histogram
                    fig_hist = px.histogram(
                        df_filtered, x="Profit/Loss", nbins=30, # Adjust nbins as needed
                        title="Distribution of Trade P/L"
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)

                # Row 3: Instrument Analysis
                col1, col2 = st.columns(2)
                with col1:
                     # P/L by Instrument Bar Chart
                     fig_inst_pl = px.bar(
                         pl_by_instrument.sort_values('Profit/Loss', ascending=False), # Sort for clarity
                         x='Instrument', y='Profit/Loss',
                         color='Profit/Loss', # Color bars based on P/L value
                         color_continuous_scale=px.colors.diverging.RdYlGn, # Red-Yellow-Green scale
                         title="Total P/L by Instrument"
                     )
                     st.plotly_chart(fig_inst_pl, use_container_width=True)
                with col2:
                     # Trade Count by Instrument Bar Chart
                     fig_inst_count = px.bar(
                         count_by_instrument.sort_values('Count', ascending=False), # Sort for clarity
                         x='Instrument', y='Count',
                         title="Trade Count by Instrument"
                     )
                     st.plotly_chart(fig_inst_count, use_container_width=True)


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
        st.exception(e) # Show details

if __name__ == "__main__":
    main()