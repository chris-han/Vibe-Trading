#!/bin/bash
# Feishu Permission Verification Script for semantier bot
# Usage: ./feishu_permission_check.sh

set -e

APP_ID="cli_a95e5e0371211bd3"
APP_SECRET="j4sWTpFKIVrPafoh7mzCVnb1lrFXpylq"

echo "=== Getting tenant access token ==="
TOKEN=$(curl -s -X POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal \
  -H "Content-Type: application/json" \
  -d "{\"app_id\":\"$APP_ID\",\"app_secret\":\"$APP_SECRET\"}" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tenant_access_token',''))")

if [ -z "$TOKEN" ]; then
    echo "Failed to get token"
    exit 1
fi

echo "=== Checking app scopes ==="
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://open.feishu.cn/open-apis/application/v6/applications/$APP_ID?lang=zh_cn" | python3 -c "
import sys, json
d = json.load(sys.stdin)
app = d.get('data', {}).get('app', {})
scopes = app.get('scopes', [])

required = [
    'contact:department.organize:readonly',
    'contact:department.base:readonly',
    'contact:user.id:readonly',
    'contact:user.department:readonly',
]

current = {s.get('scope') for s in scopes}
print(f'\\nApp: {app.get(\"app_name\")} ({app.get(\"app_id\")})')
print(f'Total scopes: {len(scopes)}')
print('\\n--- Required Permission Status ---')
all_granted = True
for r in required:
    status = '✅ GRANTED' if r in current else '❌ MISSING'
    if r not in current:
        all_granted = False
    print(f'  {status} {r}')

if all_granted:
    print('\\n🎉 All required permissions are granted!')
else:
    print('\\n⚠️  Some permissions are still missing. Wait for admin approval or re-apply.')
"

echo -e "\n=== Testing department listing ==="
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://open.feishu.cn/open-apis/contact/v3/departments?department_id_type=open_department_id&page_size=10" | python3 -c "
import sys, json
d = json.load(sys.stdin)
items = d.get('data', {}).get('items', [])
if items:
    print(f'✅ Can list departments: {len(items)} found')
    for dept in items:
        print(f'  - {dept.get(\"name\", \"???\")} ({dept.get(\"open_department_id\", \"\")})')
else:
    code = d.get('code', 0)
    if code == 0:
        print('⚠️  API succeeded but no departments returned (org may be flat)')
    else:
        print(f'❌ Failed: {d.get(\"msg\", \"unknown error\")} (code={code})')
"

echo -e "\n=== Testing user search ==="
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST \
  "https://open.feishu.cn/open-apis/contact/v3/users/search?user_id_type=open_id" \
  -d '{"query":"Henry wang"}' | python3 -c "
import sys, json
d = json.load(sys.stdin)
users = d.get('data', {}).get('users', [])
if users:
    print(f'✅ Can search users: {len(users)} match(es) for \"Henry wang\"')
    for u in users:
        print(f'  - {u.get(\"name\", \"???\")} ({u.get(\"open_id\", \"\")})')
else:
    code = d.get('code', 0)
    if code == 0:
        print('ℹ️  Search API works but no user named \"Henry wang\" found')
    else:
        print(f'❌ Search failed: {d.get(\"msg\", \"unknown error\")} (code={code})')
"

echo -e "\n=== Done ==="
