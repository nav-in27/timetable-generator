import urllib.request
import time
import json

url = "http://localhost:8000/api/teachers/"
try:
    start = time.time()
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.loads(response.read().decode())
        end = time.time()
        print(f"Status Code: {response.getcode()}")
        print(f"Time Taken: {end - start:.2f}s")
        print(f"Teacher count: {len(data)}")
        if len(data) > 0:
            print(f"First teacher: {data[0]['name']}")
            print(f"Assignments for first teacher: {len(data[0].get('class_assignments', []))}")
except Exception as e:
    print(f"Request failed: {e}")
