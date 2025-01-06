## iCal test

import requests

# Replace with the actual iCalendar public URL
ics_url = 'https://calendar.google.com/calendar/ical/0a1d3a95d78a666e49d2824aaf20156f25e6aa64f868eff8f737ede23a3eb247%40group.calendar.google.com/public/basic.ics'

import requests
from icalendar import Calendar
from datetime import datetime

# Fetch the public .ics file (can be from a URL or local file)
response = requests.get(ics_url)

# Parse the iCalendar data
calendar = Calendar.from_ical(response.content)

# Print the events
for component in calendar.walk():
    if component.name == "VEVENT":
        summary = component.get('summary')
        start_time = component.get('dtstart').dt
        end_time = component.get('dtend').dt
        print(f"Event: {summary}")
        print(f"Start: {start_time}")
        print(f"End: {end_time}")
        print('---')
