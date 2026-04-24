import os
import requests

def test():
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    
    # Get token
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret}
    )
    print(f"Token response: {resp.status_code}")
    print(resp.json())
    token = resp.json().get("tenant_access_token")
    
    # Try the failing endpoint
    params = {
        "department_id": "0",
        "department_id_type": "department_id",
        "user_id_type": "open_id",
        "page_size": 100,
    }
    resp = requests.get(
        "https://open.feishu.cn/open-apis/contact/v3/users/find_by_department",
        headers={"Authorization": f"Bearer {token}"},
        params=params
    )
    print(f"Endpoint response: {resp.status_code}")
    try:
        print(resp.json())
    except:
        print(resp.text)

if __name__ == "__main__":
    test()
