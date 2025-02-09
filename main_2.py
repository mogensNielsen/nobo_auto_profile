from collections import OrderedDict
from datetime import datetime, timedelta

def add_dates_to_profile(data):
    # Second argument is the default. I.e. an empty list
    profile = data.get('profile', [])
    today = datetime.today()
    days_of_week =['Monday', 'Tueday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Work backwards from today to the most recent Monday
    start_date = today - timedelta(days=today.weekday())

    # Identify the start indexes for each day
    day_indexes = [i for i, v in enumerate(profile) if v.startswith('0000')]

    if len(day_indexes) != 7:
        raise ValueError('Expected exactly 7 days in the profile data')

    # Create a dictionary mapping each date to its corresponding values
    dated_profile = OrderedDict()
    for i in range(7):
        date_str = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        start_index = day_indexes[i]
        end_index = day_indexes[i + 1] if i < 6 else len(profile)
        dated_profile[date_str] = profile[start_index:end_index]

    return dated_profile

# Example usage
data = OrderedDict({
    'week_profile_id': '24',
    'name': 'python_test',
    'profile': [
        '00001', '01001', '02001', '03001', '04001', '05001', '06001',
        '07002', '08002', '09002', '10002', '11000', '12000', '13001',
        '14001', '15001', '16000', '17000', '18000', '19000', '20001',
        '21001', '22001', '23001', '00000', '00000', '00000', '00000',
        '00000', '00000'
    ]
})

result = add_dates_to_profile(data)
for date, value in result.items():
    print(f'{date}: {value}')
