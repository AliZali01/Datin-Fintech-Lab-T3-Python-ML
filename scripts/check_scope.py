
from urllib.parse import urlencode
from urllib.request import urlopen
import json

endpoint = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"

params = {
    "$select": "complaint_type,count(*) as records",
    "$where": (
        "created_date >= '2024-01-01T00:00:00' "
        "AND created_date < '2025-07-01T00:00:00'"
    ),
    "$group": "complaint_type",
    "$order": "records DESC",
    "$limit": 20,
}

url = f"{endpoint}?{urlencode(params)}"

with urlopen(url, timeout=30) as response:
    rows = json.load(response)

for row in rows:
    print(f"{row.get('complaint_type')}: {row.get('records')}")
