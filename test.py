# import requests

# API_KEY = "YOUR_TAVUS_API_KEY"
# r = requests.get("https://tavusapi.com/v2/replicas",
#                  headers={"x-api-key": API_KEY},
#                  params={"limit": 20})
# for rep in r.json().get("data", []):
#     print(rep["replica_id"], "|", rep.get("replica_name"), "|", rep.get("status"))

import requests

API_KEY = "YOUR_TAVUS_API_KEY"
CONV_ID = "ce4190f1fc4f54e0"  # 你之前那个 conversation ID

r = requests.get(
    f"https://tavusapi.com/v2/conversations/{CONV_ID}",
    headers={"x-api-key": API_KEY}
)
print(r.json())