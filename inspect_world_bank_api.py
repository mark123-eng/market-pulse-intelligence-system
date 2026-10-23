import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_URL = "https://search.worldbank.org/api/v3/projects"

params = {
    "format": "json",
    "rows": 3,
    "os": 0,
    "countrycode_exact": "KE",
    "status_exact": "Active",
}

url = f"{API_URL}?{urlencode(params)}"

request = Request(
    url,
    headers={"User-Agent": "MarketPulse/1.0"},
)

with urlopen(request, timeout=30) as response:
    payload = json.loads(response.read().decode("utf-8"))

print("\nTOP-LEVEL RESPONSE KEYS:")
print(list(payload.keys()))

projects = payload.get("projects", {})

print("\nNUMBER OF PROJECTS RETURNED:", len(projects))

for project_id, record in list(projects.items())[:3]:
    print(f"\n{'=' * 60}")
    print("PROJECT ID:", project_id)
    print("AVAILABLE FIELDS:")
    print(list(record.keys()))

    print("\nPOTENTIAL STATUS FIELDS:")
    for key, value in record.items():
        if "status" in key.lower():
            print(f"{key}: {value}")

    print("\nRECORD SAMPLE:")
    print(json.dumps(record, indent=2, ensure_ascii=False))