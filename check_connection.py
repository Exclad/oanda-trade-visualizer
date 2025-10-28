import configparser
import oandapyV20
import oandapyV20.endpoints.accounts as accounts
from oandapyV20.exceptions import V20Error

def get_config():
    """
    Reads the configuration file (config.ini) to get API credentials.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    if 'OANDA' not in config:
        raise ValueError("Config file 'config.ini' not found or 'OANDA' section is missing.")
        
    return config['OANDA']

def connect_to_oanda(config):
    """
    Uses the config details to create and return an API client.
    """
    account_id = config['ACCOUNT_ID']
    access_token = config['ACCESS_TOKEN']
    environment = config['ENVIRONMENT']  # 'practice' or 'live'
    
    api = oandapyV20.API(access_token=access_token, environment=environment)
    return api, account_id

def main():
    print("--- Testing Oanda Connection ---")
    try:
        config = get_config()
        api, account_id = connect_to_oanda(config)
        
        print(f"Attempting to connect to Account ID: {account_id} on {config['ENVIRONMENT']}...")
        
        # This is a simple API call to just get your account summary
        r = accounts.AccountSummary(accountID=account_id)
        api.request(r)
        
        print("\n--- SUCCESS! ---")
        print("Connection successful. Received account summary:")
        print(r.response)
        
        if 'account' in r.response and 'balance' in r.response['account']:
            print(f"\nYour account balance is: {r.response['account']['balance']}")

    except V20Error as err:
        print(f"\n--- OANDA API ERROR ---")
        print(f"The API returned an error: {err}")
        print("Please check your 'ACCOUNT_ID' and 'ACCESS_TOKEN' in config.ini")

    except Exception as e:
        print(f"\n--- AN ERROR OCCURRED ---")
        print(e)
        print("Please check your 'config.ini' file.")

if __name__ == "__main__":
    main()