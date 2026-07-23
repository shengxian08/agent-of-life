import sys, json, urllib.request
url = "http://localhost:8000/api/v1/knowledge/list?limit=80"
data = json.loads(urllib.request.urlopen(url).read())
for doc in data["documents"]:
    print(f'【{doc["index"]}】{doc["content_preview"]}')
    print()
