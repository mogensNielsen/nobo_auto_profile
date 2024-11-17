import asyncio
from pynobo import nobo
from dotenv import load_dotenv
import os
import requests
import pandas as pd
from datetime import datetime

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
            total # Totalpris uten nettleie
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

# Define the mapping dictionary
# 0: ECO
# 1: COMFORT
# 2: AWAY
# 4: OFF
level_to_mode = {
    'VERY_CHEAP': 1,
    'CHEAP': 1,
    'NORMAL': 0,
    'EXPENSIVE': 2,
    'VERY_EXPENSIVE': 2
}

# Create the new DataFrame with the mode column added
df_prices_with_mode = df_tibber_prices.copy()
df_prices_with_mode['mode'] = df_prices_with_mode['level'].map(level_to_mode)

# The complete profile needs to have one entry for midnight pr day
# The profile data I have is only for tomorrow so I need to a number of midnight rows before and after tomorrow
iso_day_number = datetime.today().isoweekday()
nr_of_days_before_tomorrow = iso_day_number
if iso_day_number == 7:
  nr_of_days_after_tomorrow = 0
else:
   nr_of_days_after_tomorrow = 7 - iso_day_number - 1

empty_row = [0, '2024-11-14', '00:00:00', 0, 0]

# Convert the empty_row into a DataFrame with the same column names as the original DataFrame
top_rows = pd.DataFrame([empty_row] * nr_of_days_before_tomorrow, columns=df_prices_with_mode.columns)
bottom_rows = pd.DataFrame([empty_row] * nr_of_days_after_tomorrow, columns=df_prices_with_mode.columns)

# Concatenate the rows at the top and bottom
df_week_profile = pd.concat([top_rows, df_prices_with_mode, bottom_rows], ignore_index=True)

df_week_profile = df_week_profile.astype({
    'total': 'float64', 
    'starts_at_date': 'datetime64[ns]', 
    'starts_at_time': 'string', 
    'level': 'object', 
    'mode': 'int64'
})

# Create the list that is needed to set a week profile
# Each item in the list is [HHMML]
# where HH is the hour, MM is minutes and L is the mode (level) (ECO, COMFORT etc.)
list_week_profile = [
  f'{row["starts_at_time"][:2]}{row["starts_at_time"][3:5]}{row["mode"]}'
  # iterrows returns index and row values as column names
  # The _ is a placeholder for the row's index
  # It basically means "I'm acknowledging this part of the output but don’t need to do anything with it."
  for _, row in df_week_profile.iterrows()
]

hub_last_serial = os.getenv('HUB_LAST_SERIAL')

async def main():
    # Call using the three last digits in the hub serial
    hub = nobo(hub_last_serial, synchronous=False)

    # Connect to the hub and get initial data
    await hub.connect()

    # This function is called whenever the hub updates something
    def update(hub):
        print('Updating hub')
        #print(hub.week_profiles)

    # Read the initial data
    update(hub)

    # Try to update a week profile
    # Something is wrong with the list, I get an error saying it should be exactly 7 entries for midnight
    # I found out that there needs to be exactly 7 entries in the list that are `0000[mode]`. Don't know how I'm going to implement that right now
    await hub.async_update_week_profile(week_profile_id='24', name='python_test', profile=list_week_profile)

    #print(hub.week_profiles)
    # Example of using a function
    # zone_id 1 is the zone for the second floor
    #print(hub.get_current_zone_mode(zone_id='1'))

    # dict_zones = {}

    # for key, ordered_dict in hub.zones.items():
    #     dict_zones[key] = ordered_dict['name'].replace('\xa0', ' ')

    # print(dict_zones)

    # print('------')
    # hub.create_override(
    #     mode=nobo.API.OVERRIDE_MODE_COMFORT,
    #     type=nobo.API.OVERRIDE_TYPE_NOW,
    #     target_type=nobo.API.OVERRIDE_TARGET_ZONE,
    #     target_id='1' # Zone for second floor
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