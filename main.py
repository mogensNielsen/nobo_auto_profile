# Imports
import asyncio
from pynobo import nobo
from dotenv import load_dotenv
import os
import requests
import pandas as pd
from datetime import datetime, time, timedelta
from collections import OrderedDict

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

def add_weekdays_to_profile(data):
    # Second argument is the default. I.e. an empty list
    profile = data.get('profile', [])
    days_of_week =['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

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
    hourly_dict = OrderedDict()

    # Convert date to weekday
    # The `to_datetime` ensures that the value is of type datetime before getting the weekday with `strftime`
    weekday = pd.to_datetime(df.iloc[0]['starts_at_date']).strftime('%A')

    # Extract hourly values for the weekday
    hourly_values = [
        f'{row["starts_at_time"][:2]}00{row["mode"]}'
        for _, row in df.iterrows()
    ]

    hourly_dict[weekday] = hourly_values

    return hourly_dict

# Checks if all environment variables are set
if not all([tibber_url, tibber_token, tibber_home_id, hub_last_serial]):
   raise ValueError("Environment variables TIBBER_TOKEN, TIBBER_HOME_ID, or HUB_LAST_SERIAL are missing.")

async def main():
    # Connect to the hub to fetch the current week profiles
    hub = nobo(hub_last_serial, synchronous=False)
    await hub.connect()

    # Fetch the current week profile
    current_week_profile = hub.week_profiles['24']

    # Disconnect from the hub before fetching prices
    await hub.stop()

    # Add weekdays to the current week profile
    current_weekday_profile = add_weekdays_to_profile(current_week_profile)

    # Get Tibber prices and create a week profile
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
    except (KeyError, TypeError) as e:
        raise ValueError(f"Unexpected response structure: {e}")

    # Check if there are any prices in the response
    try:
        if not dict_tibber_response['data']['viewer']['home']['currentSubscription']['priceInfo']['tomorrow']:
            print("No prices available yet")
            exit(0)
    except KeyError:
        print("Price information is missing, likely not ready yet")
        exit(0)


    df_tibber_prices = pd.DataFrame(dict_tibber_prices)

    # Convert 'startsAt' to datetime and extract date and time components
    df_tibber_prices['startsAt'] = pd.to_datetime(df_tibber_prices['startsAt'])
    df_tibber_prices['starts_at_date'] = df_tibber_prices['startsAt'].apply(lambda x: x.date())
    df_tibber_prices['starts_at_time'] = df_tibber_prices['startsAt'].apply(lambda x: x.time())

    # Select and rename columns as needed
    df_tibber_prices = df_tibber_prices[['total', 'starts_at_date', 'starts_at_time', 'level']]

    # Create the new DataFrame with the mode column added
    df_tibber_prices_with_modes = df_tibber_prices.copy()
    df_tibber_prices_with_modes['mode'] = df_tibber_prices_with_modes['level'].map(level_to_mode)

    df_week_profile = df_tibber_prices_with_modes.astype({
        'total': 'float64',
        'starts_at_date': 'datetime64[ns]',
        'starts_at_time': 'string',
        'level': 'object',
        'mode': 'int64'
    })

    # # Create the list that is needed to set a week profile
    # # Each item in the list is in the format [HHMML]
    # # where HH is the hour, MM is minutes and L is the mode (level) (ECO, COMFORT etc.)
    # list_week_profile = [
    # f'{row["starts_at_time"][:2]}{row["starts_at_time"][3:5]}{row["mode"]}'
    # # iterrows returns index and row values as column names
    # # The _ is a placeholder for the row's index
    # # It basically means "I'm acknowledging this part of the output but don’t need to do anything with it."
    # for _, row in df_week_profile.iterrows()
    # ]

    dict_tibber = create_hourly_dict(df_week_profile)

    todays_date = datetime.today()
    tomorrows_date = todays_date + timedelta(days=1)
    tomorrows_weekday = tomorrows_date.strftime('%A')

    current_weekday_profile[tomorrows_weekday] = dict_tibber[tomorrows_weekday]
    print(type(current_weekday_profile))
    print(current_weekday_profile)

    list_week_profile = []
    for weekday, values in current_weekday_profile.items():
        for value in values:
            list_week_profile.append(value)

    print(f'List: {list_week_profile}')

    # --- Now reconnect to update the week profile ---
    hub = nobo(hub_last_serial, synchronous=False)
    await hub.connect()

    # This function is called whenever the hub updates something
    def update(hub):
        print('Updating hub')

    update(hub)

    # Update the week profile
    await hub.async_update_week_profile(
        week_profile_id='24',
        name='python_test',
        profile=list_week_profile
    )

    hub.register_callback(callback=update)

    await hub.start()
    await asyncio.sleep(60)
    await hub.stop()

asyncio.run(main())
