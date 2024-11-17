# Imports
import asyncio
from pynobo import nobo
from dotenv import load_dotenv
import os
import requests
import pandas as pd
from datetime import datetime, time

# Load environment variables
load_dotenv()

# Constants
tibber_url = 'https://api.tibber.com/v1-beta/gql'
tibber_token = os.getenv('TIBBER_TOKEN')
tibber_home_id = os.getenv('TIBBER_HOME_ID')
hub_last_serial = os.getenv('HUB_LAST_SERIAL')
tibber_query = f'''
{{
  viewer {{
    home(id: "{tibber_home_id}") {{
      currentSubscription {{
        priceInfo {{
          tomorrow {{ # Prices for tomorrow
            total     # Total price incl. taxes but excluding net rent (nettleie)
            startsAt  # Start time for the price
            level     # Price level, e.g. CHEAP, NORMAL
          }}
        }}
      }}
    }}
  }}
}}
'''

# Variables
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {tibber_token}"
}

def calc_days_before_after():
   today = datetime.now().weekday()
   tomorrow = (today + 1) % 7 # Ensure wraparound
   days_before = tomorrow
   days_after = 6 - tomorrow
   return days_before, days_after


if not all([tibber_url, tibber_token, tibber_home_id, hub_last_serial]):
   raise ValueError("Environment variables TIBBER_TOKEN, TIBBER_HOME_ID, or HUB_LAST_SERIAL are missing.")

tibber_response = requests.post(
   tibber_url,
   json={'query': tibber_query},
   headers=headers
)

if tibber_response.status_code != 200:
   raise ValueError(f"Tibber API error: {tibber_response.status_code}, {tibber_response.text}")

try:
   dict_tibber_response = tibber_response.json()
   dict_tibber_prices = (
      dict_tibber_response['data']
        ['viewer']
        ['home']
        ['currentSubscription']
        ['priceInfo']
        ['tomorrow']
    )
except(KeyError, TypeError) as e:
   raise ValueError(f"Unexpected response structure: {e}")

df_tibber_prices = pd.DataFrame(dict_tibber_prices)

# Convert 'startsAt' to datetime and extract date and time components
df_tibber_prices['startsAt'] = pd.to_datetime(df_tibber_prices['startsAt'])
df_tibber_prices['starts_at_date'] = df_tibber_prices['startsAt'].apply(lambda x: x.date())
df_tibber_prices['starts_at_time'] = df_tibber_prices['startsAt'].apply(lambda x: x.time())

# Select and rename columns as needed
df_tibber_prices = df_tibber_prices[['total', 'starts_at_date', 'starts_at_time', 'level']]

# Define the mapping dictionary
# This is used to map between price level and heating mode in Nobo
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
df_tibber_prices_with_modes = df_tibber_prices.copy()
df_tibber_prices_with_modes['mode'] = df_tibber_prices_with_modes['level'].map(level_to_mode)

# The complete profile needs to have one entry for midnight for each day of the week
# The profile data I have is only for tomorrow so I need to add a number of midnight
# rows before and after tomorrow
nr_of_days_before_today, nr_of_days_after_today = calc_days_before_after()

placeholder_row = {
    'total': 0.0,
    'starts_at_date': pd.Timestamp('2024-11-14'),
    'starts_at_time': time(0, 0).strftime('%H:%M:%S'),
    'level': 'NORMAL',
    'mode': 0
}

# Convert the placeholder_row into a DataFrame with the same column names as the original DataFrame
pre_today_rows = pd.DataFrame(
   [placeholder_row] * nr_of_days_before_today,
   columns=df_tibber_prices_with_modes.columns
)
post_today_rows = pd.DataFrame(
   [placeholder_row] * nr_of_days_after_today,
   columns=df_tibber_prices_with_modes.columns
)

df_week_profile = pd.concat(
    [
        pre_today_rows if not pre_today_rows.empty else None, # If the df is empty, concat with None
        df_tibber_prices_with_modes,
        post_today_rows if not post_today_rows.empty else None, # If the df is empty, concat with None
    ],
    ignore_index=True
)

df_week_profile = df_week_profile.astype({
    'total': 'float64', 
    'starts_at_date': 'datetime64[ns]', 
    'starts_at_time': 'string', 
    'level': 'object', 
    'mode': 'int64'
})

# Create the list that is needed to set a week profile
# Each item in the list is in the format [HHMML]
# where HH is the hour, MM is minutes and L is the mode (level) (ECO, COMFORT etc.)
list_week_profile = [
  f'{row["starts_at_time"][:2]}{row["starts_at_time"][3:5]}{row["mode"]}'
  # iterrows returns index and row values as column names
  # The _ is a placeholder for the row's index
  # It basically means "I'm acknowledging this part of the output but don’t need to do anything with it."
  for _, row in df_week_profile.iterrows()
]

async def main():
    # Call using the three last digits in the hub serial
    hub = nobo(hub_last_serial, synchronous=False)

    # Connect to the hub and get initial data
    await hub.connect()

    # This function is called whenever the hub updates something
    def update(hub):
        print('Updating hub')

    # Read the initial data
    update(hub)

    # Update the week profile
    await hub.async_update_week_profile(
       week_profile_id='24',
       name='python_test',
       profile=list_week_profile
    )

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