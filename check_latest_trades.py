import configparser
import requests
import json

def get_config():
    """
    Reads the configuration file (config.ini).
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    if 'OANDA' not in config:
        raise ValueError("Config file 'config.ini' not found.")
    return config['OANDA']

def main():
    try:
        config = get_config()
        account_id = config['ACCOUNT_ID']
        access_token = config['ACCESS_TOKEN']
        environment = config['ENVIRONMENT']
        
        # --- 1. Set up the connection details ---
        base_url = ""
        if environment == 'live':
            base_url = "https://api-fxtrade.oanda.com"
        else:
            base_url = "https://api-fxpractice.oanda.com"
            
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # --- 2. Get the REAL lastTransactionID ---
        summary_url = f"{base_url}/v3/accounts/{account_id}/summary"
        summary_response = requests.get(summary_url, headers=headers)
        summary_data = summary_response.json()
        
        true_last_id = int(summary_data['account']['lastTransactionID'])
        print(f"--- Connected to {account_id} ---")
        print(f"Live Balance: {summary_data['account']['balance']}")
        print(f"Live lastTransactionID: {true_last_id}")

        # --- 3. Make paginated API calls ---
        all_transactions = []
        current_from_id = 1
        page_size = 1000  # We know this is the limit
        
        print("\n--- Fetching transactions in chunks... ---")

        while current_from_id <= true_last_id:
            current_to_id = min(current_from_id + page_size - 1, true_last_id)
            
            print(f"Fetching chunk: IDs {current_from_id} to {current_to_id}...")
            
            transactions_url = f"{base_url}/v3/accounts/{account_id}/transactions/idrange"
            params = {
                "from": str(current_from_id),
                "to": str(current_to_id)
            }
            
            response = requests.get(transactions_url, headers=headers, params=params)
            data = response.json()
            
            if 'transactions' not in data:
                print(f"Error in chunk {current_from_id}-{current_to_id}: {data}")
                break

            chunk_transactions = data.get('transactions', [])
            if not chunk_transactions:
                break

            all_transactions.extend(chunk_transactions)
            current_from_id = current_to_id + 1

        # --- 4. Process the (correct) full data ---
        print(f"\nSUCCESS! Fetched a total of {len(all_transactions)} transactions.")

        # --- 5. Find the trades with P/L ---
        print("\n--- Finding all trades with realized P/L ---")
        found_trades = 0
        for t in all_transactions:
            if 'pl' in t and float(t['pl']) != 0:
                found_trades += 1
                
                # --- THIS IS THE FIX ---
                # Compare int(t['id']) to 1000
                if int(t['id']) > 1000:
                # --- END OF FIX ---
                    print(f"  > Found NEW Trade! ID: {t['id']}, Time: {t['time']}, P/L: {t['pl']}")
                else:
                    # Old trade, don't print
                    pass 
        
        if found_trades == 0:
            print("No trades with P/L were found in the full transaction list.")
        else:
            print(f"\n--- Found a total of {found_trades} closed trades. ---")
            
            print("\n--- Verifying recent trades from your screenshot: ---")
            for t in all_transactions:
                # Compare string to string is fine
                if t['id'] == '1229':
                    print(f"  > Found ID 1229! P/L: {t['pl']} (Should be 62.09)")
                if t['id'] == '1222':
                    print(f"  > Found ID 1222! P/L: {t['pl']} (Should be -21.09)")
                if t['id'] == '1217':
                    print(f"  > Found ID 1217! P/L: {t['pl']} (Should be -10.10)")

    except Exception as e:
        print(f"\n--- An error occurred ---")
        print(e)

if __name__ == "__main__":
    main()