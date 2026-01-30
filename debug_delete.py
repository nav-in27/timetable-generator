import urllib.request
import urllib.error
import json

BASE_URL = "http://127.0.0.1:8000/api"

def debug_delete():
    print(f"Connecting to {BASE_URL}...")
    
    # 1. Create a teacher with no email (using new logic)
    print("Creating teacher...")
    payload = {
        "name": "Delete Test Teacher",
        "email": "", # Send empty string to test the fix in create_teacher
        "max_hours_per_week": 20,
        "experience_years": 5,
        "experience_score": 0.5,
        "available_days": "1,2,3,4,5",
        "subject_ids": []
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        req = urllib.request.Request(
            f"{BASE_URL}/teachers/", 
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            print(f"Create status: {response.getcode()}")
            data = json.load(response)
            t_id = data["id"]
            print(f"Created teacher ID: {t_id}")
            
            # 2. Delete the teacher
            print(f"Deleting teacher {t_id}...")
            del_req = urllib.request.Request(
                f"{BASE_URL}/teachers/{t_id}",
                method="DELETE"
            )
            with urllib.request.urlopen(del_req) as del_response:
                print(f"Delete status: {del_response.getcode()}")
                if del_response.getcode() == 204:
                    print("Delete successful!")
                else:
                    print(f"Delete returned code: {del_response.getcode()}")
                    
    except urllib.error.HTTPError as e:
        print(f"HTTPError: {e.code} - {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    debug_delete()
