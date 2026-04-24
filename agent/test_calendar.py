import os
import requests
import json

def _env(name):
    return os.environ.get(name)

def _base_url():
    domain = _env("FEISHU_DOMAIN") or "feishu"
    return f"https://open.{domain}.cn"

def _http_json(method, url, headers=None, body=None, params=None):
    res = requests.request(method, url, headers=headers, json=body, params=params)
    print(f"DEBUG: {method} {url} -> {res.status_code}")
    try:
        return res.json()
    except:
        return {"error": "not json", "text": res.text}

def get_token():
    app_id = _env("FEISHU_APP_ID")
    app_secret = _env("FEISHU_APP_SECRET")
    data = _http_json("POST", f"{_base_url()}/open-apis/auth/v3/tenant_access_token/internal", body={"app_id": app_id, "app_secret": app_secret})
    return data.get("tenant_access_token")

token = get_token()
if token:
    print("GOT TOKEN")
    # Try primary calendar
    cal = _http_json("POST", f"{_base_url()}/open-apis/calendar/v4/calendars/primary", headers={"Authorization": f"Bearer {token}"})
    print("PRIMARY CALENDAR RESPONSE:")
    print(json.dumps(cal, indent=2))
    
    # Try user search
    search = _http_json("GET", f"{_base_url()}/open-apis/contact/v3/users/find_by_department", params={"department_id": "0"}, headers={"Authorization": f"Bearer {token}"})
    print("USER SEARCH RESPONSE:")
    print(json.dumps(search, indent=2))
else:
    print("FAILED TO GET TOKEN")
