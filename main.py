# Imports
import asyncio
from pynobo import nobo
from dotenv import load_dotenv
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from collections import OrderedDict

# Load environment variables
load_dotenv()

# Constants
TIBBER_URL = 'https://api.tibber.com/v1-beta/gql'
TIBBER_TOKEN = os.getenv('TIBBER_TOKEN')
TIBBER_HOME_ID = os.getenv('TIBBER_HOME_ID')
HUB_LAST_SERIAL = os.getenv('HUB_LAST_SERIAL')

TIBBER_QUERY = f'''
{{
  viewer {{
    home(id: "{TIBBER_HOME_ID}") {{
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
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TIBBER_TOKEN}"
}

# Define the mapping dictionary
# This is used to map between price level and heating mode in Nobo
# 0: ECO
# 1: COMFORT
# 2: AWAY
# 4: OFF
LEVEL_TO_MODE = {
    'VERY_CHEAP': 1,
    'CHEAP': 1,
    'NORMAL': 0,
    'EXPENSIVE': 2,
    'VERY_EXPENSIVE': 2
}

def validate_env_variables():
    """ Ensure all required environment variables are set. """
    if not all([TIBBER_URL, TIBBER_TOKEN, TIBBER_HOME_ID, HUB_LAST_SERIAL]):
        raise ValueError("Missing required environment variables: TIBBER_TOKEN, TIBBER_HOME_ID, HUB_LAST_SERIAL.")

def fetch_tibber_prices():
    """ Fetch Tibber prices and return as a Pandas DataFrame. """
    response = requests.post(TIBBER_URL, json={'query': TIBBER_QUERY}, headers=HEADERS)

    if response.status_code != 200:
        raise ValueError(f"Tibber API error: {response.status_code}, {response.text}")

    try:
        tibber_data = response.json()
        tibber_prices = (
            tibber_data['data']['viewer']['home']['currentSubscription']['priceInfo']['tomorrow']
        )

        if not tibber_prices:
            print("No prices available yet. Exiting...")
            exit(1)

    except (KeyError, TypeError) as e:
        raise ValueError(f"Unexpected response structure: {e}")

    # Convert to DataFrame
    df = pd.DataFrame(tibber_prices)
    df['startsAt'] = pd.to_datetime(df['startsAt'])
    df['starts_at_date'] = df['startsAt'].dt.date
    df['starts_at_time'] = df['startsAt'].dt.strftime("%H:%M:%S")

    df = df[['total', 'starts_at_date', 'starts_at_time', 'level']]
    df['mode'] = df['level'].map(LEVEL_TO_MODE)

    return df.astype({
        'total': 'float64',
        'starts_at_date': 'datetime64[ns]',
        'starts_at_time': 'string',
        'level': 'object',
        'mode': 'int64'
    })

def add_weekdays_to_profile(data):
    """ Convert profile data into a dictionary with weekdays as keys. """
    # Second argument is the default. I.e. an empty list
    profile = data.get('profile', [])
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Identify the start indexes for each day
    day_indexes = [i for i, v in enumerate(profile) if v.startswith('0000')]

    if len(day_indexes) != 7:
        raise ValueError('Expected exactly 7 days in the profile data')

    # Create a dictionary mapping each weekday to its corresponding values
    weekday_profile = OrderedDict()
    for i in range(7):
        weekday = days_of_week[i]
        start_index = day_indexes[i]
        end_index = day_indexes[i + 1] if i < 6 else len(profile)
        weekday_profile[weekday] = profile[start_index:end_index]

    return weekday_profile

def create_hourly_dict(df):
    """ Create an hourly dictionary with weekday as the key. """
    hourly_dict = OrderedDict()

    # Convert date to weekday
    # The `to_datetime` ensures that the value is of type datetime before getting the weekday with `strftime`
    weekday = df['starts_at_date'].iloc[0].strftime('%A')

    # Extract hourly values for the weekday
    hourly_values = [
        f'{row["starts_at_time"][:2]}00{row["mode"]}'
        for _, row in df.iterrows()
    ]

    hourly_dict[weekday] = hourly_values

    return hourly_dict

async def connect_to_hub():
    """ Connect to the Nobo hub. """
    hub = nobo(HUB_LAST_SERIAL, synchronous=False)
    await hub.connect()
    return hub

async def update_nobo_profile(hub, profile_data):
    """ Update the Nobo week profile. """
    await hub.async_update_week_profile(
        week_profile_id='24',
        name='python_test',
        profile=profile_data
    )
async def main():
    validate_env_variables()

    # --- Connect to Nobo Hub ---
    hub = await connect_to_hub()
    current_week_profile = hub.week_profiles['24']
    await hub.stop()

    # --- Process the Week Profile ---
    current_weekday_profile = add_weekdays_to_profile(current_week_profile)

    # --- Fetch Tibber Prices ---
    df_tibber_prices = fetch_tibber_prices()
    dict_tibber = create_hourly_dict(df_tibber_prices)

    # --- Update the Profile for Tomorrow ---
    tomorrow_weekday = (datetime.today() + timedelta(days=1)).strftime('%A')
    current_weekday_profile[tomorrow_weekday] = dict_tibber.get(tomorrow_weekday, [])

    # Convert to list format
    list_week_profile = [value for values in current_weekday_profile.values() for value in values]

    # --- Reconnect and Update the Week Profile ---
    hub = await connect_to_hub()
    await update_nobo_profile(hub, list_week_profile)

    await hub.start()
    await asyncio.sleep(60)
    await hub.stop()

asyncio.run(main())
