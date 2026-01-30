import urllib.request
import time

url = "http://127.0.0.1:8000/health"
try:
    start = time.time()
    with urllib.request.urlopen(url, timeout=10) as response:
        end = time.time()
        print(f"Status Code: {response.getcode()}")
        print(f"Time Taken: {end - start:.2f}s")
except Exception as e:
    print(f"Request failed: {e}")
