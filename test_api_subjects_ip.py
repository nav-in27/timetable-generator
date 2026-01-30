import urllib.request
import time
import json

url = "http://127.0.0.1:8000/api/subjects/"
try:
    start = time.time()
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.loads(response.read().decode())
        end = time.time()
        print(f"Status Code: {response.getcode()}")
        print(f"Time Taken: {end - start:.2f}s")
        print(f"Subject count: {len(data)}")
except Exception as e:
    print(f"Request failed: {e}")
