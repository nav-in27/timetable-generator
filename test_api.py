import requests
import time

url = "http://localhost:8000/api/teachers/"
try:
    start = time.time()
    response = requests.get(url, timeout=10)
    end = time.time()
    print(f"Status Code: {response.status_code}")
    print(f"Time Taken: {end - start:.2f}s")
    if response.status_code == 200:
        data = response.json()
        print(f"Teacher count: {len(data)}")
        if len(data) > 0:
            print(f"First teacher: {data[0]['name']}")
            print(f"Assignments for first teacher: {len(data[0].get('class_assignments', []))}")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Request failed: {e}")
