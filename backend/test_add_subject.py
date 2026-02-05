from fastapi.testclient import TestClient

try:
    from main import app
except Exception as e:
    print('IMPORT_ERROR', e)
    raise

client = TestClient(app)
resp = client.post('/api/elective-baskets/1/add-subject/12?allow_without_teachers=true')
print('STATUS', resp.status_code)
print(resp.text)
