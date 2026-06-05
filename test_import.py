import httpx
import json
import logging

logging.basicConfig(level=logging.INFO)

# Generate template first
r = httpx.get('http://127.0.0.1:8001/api/subjects/import/template')
with open('test_import.xlsx', 'wb') as f:
    f.write(r.content)

# Upload the template
with open('test_import.xlsx', 'rb') as f:
    r2 = httpx.post('http://127.0.0.1:8001/api/subjects/import/upload', files={'file': f})

print("UPLOAD JSON:", json.dumps(r2.json(), indent=2))

batch_id = r2.json()['batch_id']

# Commit
r3 = httpx.post(f'http://127.0.0.1:8001/api/subjects/import/commit?batch_id={batch_id}')

print("COMMIT RESULT:", json.dumps(r3.json(), indent=2))
