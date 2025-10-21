from json import dumps

from requests import get

proxies = {
    "http": "http://proxy.squirrel-regulus.ts.net:3128",
    "https": "http://proxy.squirrel-regulus.ts.net:3128",
}

response = get("https://httpbin.org/headers", proxies=proxies)

print(f"Status: {response.status_code}")
print("------------------------------------------")
print(f"Proxy used: {proxies['https']}")
print("------------------------------------------")
print("Headers that the destination server received:")
print(dumps(response.json(), indent=2))
