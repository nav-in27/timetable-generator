"""
Trigger timetable generation via API using standard library.
"""
import urllib.request
import json
import time

def trigger():
    url = "http://localhost:8000/api/timetable/generate"
    
    data = json.dumps({}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    print(f"Triggering generation at {url}...")
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            print("Generation successful!")
            # print(json.dumps(result, indent=2)) 
            # Output might be large, just print summary
            print(result.get("message", "No message"))
            print(f"Total Allocations: {result.get('total_allocations', 0)}")
            print(f"Generation Time: {result.get('generation_time_seconds', 0)}s")
            
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        print(e.read().decode('utf-8'))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    trigger()
