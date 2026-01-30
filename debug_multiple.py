import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://127.0.0.1:8000/api"

def debug_multiple():
    headers = {"Content-Type": "application/json"}
    
    try:
        # 1. Create Teacher A
        print("Creating Teacher A...")
        payload_a = {
            "name": "Teacher A",
            "email": "", 
            "max_hours_per_week": 20,
            "experience_years": 5,
            "experience_score": 0.5,
            "available_days": "1,2,3,4,5",
            "subject_ids": []
        }
        
        req_a = urllib.request.Request(
            f"{BASE_URL}/teachers/", 
            data=json.dumps(payload_a).encode('utf-8'),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req_a) as resp_a:
            data_a = json.load(resp_a)
            id_a = data_a["id"]
            print(f"Created Teacher A: ID {id_a}")
            
        # 2. Create Teacher B
        print("Creating Teacher B...")
        payload_b = {
            "name": "Teacher B",
            "email": "", 
            "max_hours_per_week": 20,
            "experience_years": 5,
            "experience_score": 0.5,
            "available_days": "1,2,3,4,5",
            "subject_ids": []
        }
        
        req_b = urllib.request.Request(
            f"{BASE_URL}/teachers/", 
            data=json.dumps(payload_b).encode('utf-8'),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req_b) as resp_b:
            data_b = json.load(resp_b)
            id_b = data_b["id"]
            print(f"Created Teacher B: ID {id_b}")

        # 3. Delete Teacher A
        print(f"Deleting Teacher A ({id_a})...")
        del_req = urllib.request.Request(
            f"{BASE_URL}/teachers/{id_a}",
            method="DELETE"
        )
        with urllib.request.urlopen(del_req) as del_response:
            print(f"Delete A status: {del_response.getcode()}")
            
        # 4. Delete Teacher B
        print(f"Deleting Teacher B ({id_b})...")
        del_req_b = urllib.request.Request(
            f"{BASE_URL}/teachers/{id_b}",
            method="DELETE"
        )
        with urllib.request.urlopen(del_req_b) as del_response_b:
            print(f"Delete B status: {del_response_b.getcode()}")

    except urllib.error.HTTPError as e:
        print(f"HTTPError: {e.code} - {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    debug_multiple()
