"""
Discovery script — run locally to:
1. Test login against belindance.wodbuster.com
2. Dump raw LoadClass.ashx JSON to understand the data structure
3. Detect Cloudflare blocking

Usage:
    WB_EMAIL=your@email.com WB_PASSWORD=yourpass python discover.py
"""
import datetime
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

email = os.environ.get("WB_EMAIL")
password = os.environ.get("WB_PASSWORD")
box_url = os.environ.get("BOX_URL", "https://belindance.wodbuster.com")

if not email or not password:
    print("Set WB_EMAIL and WB_PASSWORD environment variables")
    sys.exit(1)

sys.path.insert(0, str(__file__.rsplit("/", 1)[0]))

from belindance_booker.scraper import Scraper
from belindance_booker.exceptions import LoginError, InvalidWodBusterResponse, CloudflareBlocked

print(f"\n--- Testing login for {email} ---")
scraper = Scraper(email, password, box_url)
try:
    scraper.login()
    print("Login successful!")
except LoginError as e:
    print(f"Login failed: {e}")
    sys.exit(1)
except CloudflareBlocked as e:
    print(f"Cloudflare is blocking: {e}")
    print("Add WB_SERVER_IP to /etc/hosts or switch to cloudscraper")
    sys.exit(1)
except InvalidWodBusterResponse as e:
    print(f"Unexpected response: {e}")
    sys.exit(1)

print(f"\n--- Fetching schedule for next 7 days from {box_url} ---")
today = datetime.date.today()
for i in range(7):
    date = today + datetime.timedelta(days=i)
    try:
        data, epoch = scraper.get_classes(date)
        classes = data.get("Data") or []
        print(f"\n{date} ({len(classes)} class slots):")
        if classes:
            print(json.dumps(classes[:2], indent=2, ensure_ascii=False))
        else:
            avail = data.get("PrimeraHoraPublicacion")
            if avail:
                print(f"  Not yet published (available at: {avail})")
            else:
                print("  No classes")
    except Exception as e:
        print(f"  Error for {date}: {e}")

print("\n--- Discovery complete ---")
print("Look above for the JSON structure to identify the class name field.")
print("Search for 'CLASES PARTICULARES BELINDA' in the output.")
