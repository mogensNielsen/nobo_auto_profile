import asyncio
from pynobo import nobo
from dotenv import load_dotenv
import os
import requests
import pandas as pd
import json

load_dotenv()

tibber_url = 'https://api.tibber.com/v1-beta/gql'
tibber_token = os.getenv('TIBBER_TOKEN')
tibber_home_id = os.getenv('TIBBER_HOME_ID')

tibber_query = f'''
{{
  viewer {{
    home(id: "{tibber_home_id}") {{
      currentSubscription {{
        priceInfo {{
          tomorrow {{ # Prices for tomorrow
            total # Totalpris
            startsAt # Starttid for prisen
            level # Prisnivå, f.eks. CHEAP eller NORMAL
          }}
        }}
      }}
    }}
  }}
}}
'''

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {tibber_token}"
}

tibber_response = requests.post(tibber_url, json={'query': tibber_query}, headers=headers)

#print(tibber_response.status_code)
dict_tibber_response = tibber_response.json()

dict_tibber_prices = (
    dict_tibber_response['data']
    ['viewer']
    ['home']
    ['currentSubscription']
    ['priceInfo']
    ['tomorrow']
)

df_tibber_prices = pd.DataFrame(dict_tibber_prices)

# Convert 'startsAt' to datetime and extract date and time components
df_tibber_prices['startsAt'] = pd.to_datetime(df_tibber_prices['startsAt'])
df_tibber_prices['starts_at_date'] = df_tibber_prices['startsAt'].dt.date
df_tibber_prices['starts_at_time'] = df_tibber_prices['startsAt'].dt.time

# Select and rename columns as needed
df_tibber_prices = df_tibber_prices[['total', 'starts_at_date', 'starts_at_time', 'level']]

print(df_tibber_prices.head())

exit()

hub_last_serial = os.getenv('HUB_LAST_SERIAL')

async def main():
    # Either call using the three last digits in the hub serial
    hub = nobo(hub_last_serial, synchronous=False)
    # or full serial and IP if you do not want to discover on UDP:
    #hub = nobo('123123123123', ip='10.0.0.128', discover=False, synchronous=False)

    # Connect to the hub and get initial data
    await hub.connect()

    # This function is called whenever the hub updates something
    def update(hub):
        # print(hub.hub_info)
        # print(hub.zones)
        # print(hub.components)
        # print(hub.week_profiles)
        # print(hub.overrides)
        print(hub.temperatures)
        print('Updating hub')

    # Read the initial data
    update(hub)

    dict_zones = {}

    for key, ordered_dict in hub.zones.items():
        dict_zones[key] = ordered_dict['name'].replace('\xa0', ' ')

    print(dict_zones)

    # print('------')
    # hub.create_override(
    #     mode=nobo.API.OVERRIDE_MODE_COMFORT,
    #     type=nobo.API.OVERRIDE_TYPE_NOW,
    #     target_type=nobo.API.OVERRIDE_TARGET_ZONE,
    #     target_id='1'
    # )

    # Listen for data updates - register before calling hub.start() to avoid race condition
    hub.register_callback(callback=update)

    # Start the background tasks for reading responses and keep connction alive
    # This will connect to the hub if necessary
    await hub.start()

    # Hang around and wait for data updates
    await asyncio.sleep(60)

    # Stop the connection
    await hub.stop()

asyncio.run(main())