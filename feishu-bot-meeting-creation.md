# Feishu Bot Meeting Creation Guide

A comprehensive guide for configuring the **semantier** Feishu bot to search contacts, create meetings on user calendars, and send invitations.

---

## Table of Contents

1. [Bot Configuration](#1-bot-configuration)
2. [Required Permissions](#2-required-permissions)
3. [Contact Scope vs API Scopes](#3-contact-scope-vs-api-scopes)
4. [Authentication: Bot Token vs User Token](#4-authentication-bot-token-vs-user-token)
5. [Creating Meetings on User Calendars](#5-creating-meetings-on-user-calendars)
6. [Why Bot Calendars Cannot Be Shared](#6-why-bot-calendars-cannot-be-shared)
7. [Searching Users and Groups](#7-searching-users-and-groups)
8. [Sending Meeting Announcements](#8-sending-meeting-announcements)
9. [External Group Limitations](#9-external-group-limitations)
10. [Troubleshooting: Issues & Solutions](#10-troubleshooting-issues--solutions)

---

## 1. Bot Configuration

### Environment Variables

Set these in `agent/.env`:

```env
FEISHU_APP_ID=cli_a95e5e0371211bd3
FEISHU_APP_SECRET=j4sWTpFKIVrPafoh7mzCVnb1lrFXpylq
FEISHU_DOMAIN=feishu
FEISHU_OAUTH_ENABLED=true
FEISHU_OAUTH_APP_ID=cli_a95e5e0371211bd3
FEISHU_OAUTH_REDIRECT_URI=http://localhost:8899/auth/feishu/callback
FEISHU_SESSION_SECRET=a-long-random-stable-secret
```

### Bot Identity

| Property | Value |
|----------|-------|
| App Name | `semantier` |
| Bot Open ID | `ou_14a593652cb737715030f52a4e53fe99` |
| Status | Active (`activate_status: 2`) |

---

## 2. Required Permissions

### 2.1 API Scopes (Developer Console → Permission Management)

These control what APIs the bot can call:

| Scope | Chinese Name | Required For |
|-------|--------------|--------------|
| `contact:department.base:readonly` | 获取部门基础信息 | List departments |
| `contact:department.organize:readonly` | 获取通讯录部门组织架构信息 | Read department structure |
| `contact:user.id:readonly` | 通过手机号或邮箱获取用户 ID | Resolve users by email/name |
| `contact:user.department:readonly` | 获取用户部门信息 | List users in departments |
| `contact:user:search` | 搜索用户 | Search users by name |
| `contact:user.base:readonly` | 获取用户基本信息 | Read user basic info |
| `contact:contact.base:readonly` | 获取通讯录基本信息 | Read contact directory |
| `im:chat:readonly` | 获取群组信息 | List chats |
| `im:chat.members:read` | 查看群成员 | List chat members |
| `calendar:calendar.event:create` | 创建日程 | Create calendar events |
| `calendar:calendar.event:read` | 读取日程信息 | Read calendar events |
| `im:message:send_as_bot` | 以应用的身份发消息 | Send group messages |

**How to add:**
1. Go to [https://open.feishu.cn/app/cli_a95e5e0371211bd3/permission](https://open.feishu.cn/app/cli_a95e5e0371211bd3/permission)
2. Search for each scope and click **申请权限**
3. Go to **版本管理与发布** → create version → **申请发布**
4. Admin approves at [https://www.feishu.cn/admin/appCenter/audit](https://www.feishu.cn/admin/appCenter/audit)

### 2.2 Contact Data Scope (Application Release → Data Permissions)

This controls **which users** the bot can actually see, regardless of API scopes:

```
应用发布 → 数据权限 → 通讯录权限范围
```

| Setting | Effect |
|---------|--------|
| `指定成员` (Specified members) | Bot sees only selected users |
| `全部成员` (All members) | Bot sees entire organization |

**Verify current scope:**

```bash
GET /open-apis/contact/v3/scopes
```

**Before fix (restricted):**
```json
{
  "user_ids": [
    "ou_f2d55dbeddbcd43519c6efdf6d874712",
    "ou_11d6838db5867f5784c9853296d7f6a1"
  ]
}
```

**After fix (all members):** Should return all user IDs in the org.

---

## 3. Contact Scope vs API Scopes

### Critical Distinction

| Concept | What It Controls | Where to Configure |
|---------|-----------------|-------------------|
| **API Scopes** | Which APIs the app can call | Developer Console → 权限管理 |
| **Contact Data Scope** | Which users the app can access | Developer Console → 应用发布 → 数据权限 |

**Common mistake:** Granting all API scopes but forgetting to expand the **Contact Data Scope** to "All members". The bot will have `contact:user:search` permission but still only see 2 users.

---

## 4. Authentication: Bot Token vs User Token

### 4.1 Tenant Access Token (Bot Identity)

```bash
curl -X POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal \
  -H "Content-Type: application/json" \
  -d '{"app_id":"cli_a95e5e0371211bd3","app_secret":"j4sWTpFKIVrPafoh7mzCVnb1lrFXpylq"}'
```

**Use for:**
- ✅ Listing chats the bot is in
- ✅ Listing departments (within contact scope)
- ✅ Listing department users (within contact scope)
- ✅ Reading bot's own calendar
- ✅ Sending messages as bot

**Cannot do:**
- ❌ Search users across organization (`contact:v3/users/search` requires **user token**)

### 4.2 User Access Token (User Identity)

Required for user search and creating events on user calendars.

**Initiate device auth:**

```bash
lark-cli auth login --no-wait --json --scope "contact:department.organize:readonly contact:contact.base:readonly contact:user.base:readonly"
```

**Complete after browser authorization:**

```bash
lark-cli auth login --device-code <code-from-previous-step>
```

**Verify:**

```bash
lark-cli auth status
```

**Use for:**
- ✅ Searching users by name
- ✅ Creating events on the authorized user's calendar
- ✅ Accessing user-visible contacts

---

## 5. Creating Meetings on User Calendars

### 5.1 The Correct Pattern

**DO NOT** create events on the bot's calendar if you want them to appear on attendees' personal calendars.

**DO** create events on the organizer's (user's) calendar.

### 5.1.1 Semantier Enforcement Rule (Requester Calendar)

For semantier script-based meeting creation, the bot **must** know who the requester is:

1. **Feishu channel sessions**: `FEISHU_REQUESTER_OPEN_ID` is auto-injected by the runtime from `feishu_sender_open_id`.
2. **Web/non-Feishu channels**: The agent must pass `--requester-open-id` explicitly.

**Calendar selection logic** (implemented in `feishu_bot_api.py`):
1. Look up the requester's primary calendar via `primarys` API (batch version of `primary`).
2. Try creating the event on the requester's calendar.
3. If Feishu returns `191002 — no calendar access_role` (bot lacks write permission), **fall back to the bot's calendar**.
4. **Critical**: Set the requester as `event_organizer` so their identity appears as the organizer.
5. **Critical**: Add attendees via the **separate** `calendar_event_attendee.create` API (see §5.4). Feishu silently ignores `attendees` in the create-event body.

> **Note:** With tenant access tokens, bots typically cannot write to user calendars. The fallback to bot calendar is expected behavior. Attendees still receive proper calendar invitations as long as step 5 is followed.

### 5.2 Two-Step Event Creation (Bot Token)

When using a **tenant access token** (bot token), you cannot write directly to user calendars. The correct pattern is a **two-step creation**:

**Step 1 — Create the event skeleton** (on bot calendar or user calendar if admin permissions exist):

```bash
lark-cli api POST /open-apis/calendar/v4/calendars/:calendar_id/events --as bot \
  --data '{
    "summary": "管理层会议",
    "description": "会议描述",
    "start_time": {
      "timestamp": "1777096800",
      "timezone": "Asia/Shanghai"
    },
    "end_time": {
      "timestamp": "1777100400",
      "timezone": "Asia/Shanghai"
    },
    "vchat": {
      "vc_type": "vc"
    },
    "attendee_ability": "can_see_others",
    "visibility": "default"
  }'
```

> **Note:** `event_organizer` in the create body is **silently ignored** when creating on a bot calendar. The organizer will always display as the bot. To show a human organizer, create the event on that user's calendar using their `user_access_token`.

**Step 2 — Add attendees via dedicated API** (this is what actually sends invitations):

```bash
lark-cli api POST /open-apis/calendar/v4/calendars/:calendar_id/events/:event_id/attendees --as bot \
  --data '{
    "attendees": [
      {"type": "user", "user_id": "ou_f2d55dbeddbcd43519c6efdf6d874712", "is_optional": false},
      {"type": "user", "user_id": "ou_11d6838db5867f5784c9853296d7f6a1", "is_optional": false}
    ],
    "need_notification": true
  }'
```

> **⚠️ CRITICAL:** Feishu **silently ignores** the `attendees` field in the create-event body. You **must** use the separate `POST .../attendees` endpoint. Without this step, attendees will NOT receive invitations and the event will not appear on their calendars.

**Response (Step 1):**
```json
{
  "event": {
    "event_id": "eb51d84f-db78-4fd1-a53d-d7d5b2be0fe6_0",
    "event_organizer": {
      "display_name": "chris han",
      "user_id": "ou_f2d55dbeddbcd43519c6efdf6d874712"
    },
    "organizer_calendar_id": "feishu.cn_QdqxSNzQJJkSvAKpc9Vp9e@group.calendar.feishu.cn"
  }
}
```

### 5.3 Bot Calendar Fallback

If the bot lacks write access to the requester's calendar (error `191002`), the event is created on the **bot's calendar** as a fallback. This is safe **as long as attendees are added via the separate attendee API** (§5.2 Step 2). Attendees will still receive calendar invitations from the "日历助手" (Calendar Assistant).

**Known limitations of bot calendar:**
| Limitation | Why | Workaround |
|---|---|---|
| Organizer always shows as bot | Feishu ignores `event_organizer` on bot calendars | Accept bot identity, or use user calendar |
| `is_organizer` on attendees is ignored | Platform enforces calendar owner as organizer | N/A for bot calendar |

What does **not** work:
- Putting `attendees` inside the create-event body and expecting Feishu to send invites.
- Creating on bot calendar without the follow-up attendee API call.
- Setting `event_organizer` to fake a human organizer on bot calendar.

```bash
# DON'T do this — attendees in body are silently ignored
POST /calendars/:calendar_id/events --as bot \
  --data '{..., "attendees": [...]}'   ← IGNORED by Feishu
```

---

## 6. Why Bot Calendars Cannot Be Shared

### 6.1 Default State

Bot primary calendars are created with:

```json
{
  "permissions": "private",
  "role": "owner"
}
```

### 6.2 Changing to Public

You **can** change the permission:

```bash
PATCH /open-apis/calendar/v4/calendars/primary
{ "permissions": "public" }
```

But this only means:
- ✅ Users **can view** the event if they open the direct link
- ✅ Users **can subscribe** to the bot calendar manually

It does **NOT** mean:
- ❌ Events auto-sync to attendees' personal calendars
- ❌ Attendees see the event in their default calendar view

### 6.3 ACL Limitations

Bot calendars only support `user`-type ACL entries:

```bash
POST /calendars/{id}/acls
{ "role": "reader", "scope": { "type": "domain" } }
→ Error: "scope.type is optional, options: [user]"
```

You cannot add organization-wide (`domain`) ACLs to bot calendars.

### 6.4 The Fundamental Design

Feishu treats bot calendars as **application resources**, not **personal calendars**. The intended pattern is:

1. Bot **assists** in scheduling
2. Events are ideally created on **user calendars** (requires user token or admin privileges)
3. With bot tokens, create on **bot calendar** + add attendees via separate API
4. Bot calendars are for bot-internal scheduling only

### 6.5 Getting User Primary Calendar IDs

Use the **`primarys`** (plural) API to look up multiple users' primary calendars at once. The singular `primary` API only returns the token holder's calendar (i.e., the bot's calendar).

```bash
lark-cli api POST /open-apis/calendar/v4/calendars/primarys --as bot \
  --data '{
    "user_ids": ["ou_f2d55dbeddbcd43519c6efdf6d874712"]
  }' \
  --params '{"user_id_type":"open_id"}'
```

**Response:**
```json
{
  "calendars": [
    {
      "user_id": "ou_f2d55dbeddbcd43519c6efdf6d874712",
      "calendar": {
        "calendar_id": "feishu.cn_TeDSkx2EQ7kdVSEqMeSQFf@group.calendar.feishu.cn"
      }
    }
  ]
}
```

---

## 7. Searching Users and Groups

### 7.1 Search Users (Requires User Token)

```bash
lark-cli contact +search-user --query "Henry wang"
```

**Important:** This requires `--as user` (user access token). `--as bot` is not supported.

### 7.2 List Department Users (Bot Token)

```bash
# Within bot's contact scope
curl -H "Authorization: Bearer $TENANT_TOKEN" \
  "https://open.feishu.cn/open-apis/contact/v3/users?department_id=0&page_size=50"
```

### 7.3 Search Groups/Chats

```bash
lark-cli im +chat-search --as bot --query "管理层"
```

### 7.4 List Chat Members

```bash
lark-cli api GET /open-apis/im/v1/chats/{chat_id}/members --as bot \
  --params '{"member_id_type":"open_id","page_size":50}'
```

---

## 8. Sending Meeting Announcements

### 8.1 Send Text Message to Group

```bash
lark-cli im +messages-send --as bot \
  --chat-id "oc_747b1336232a45c7b7a8a2b14854cada" \
  --msg-type text \
  --content '{"text":"📅 会议通知\n\n主题：管理层会议\n时间：...\n链接：..."}'
```

### 8.2 Send Interactive Card (Optional)

For richer UI, use `msg-type: interactive` with a card payload. See [Feishu Card Builder](https://open.feishu.cn/tool/cardbuilder).

---

## 9. External Group Limitations

### 9.1 What We Found

The `meeting-coordinator` group was **external** (cross-tenant):

```json
{
  "chat_id": "oc_c752b8cc7dd827e0c1351261f4f8d8fa",
  "name": "meeting-coordinator",
  "external": true,
  "tenant_key": "7031788410167640066"
}
```

### 9.2 Restrictions

| Action | Result |
|--------|--------|
| List external group members | ❌ `232033` — no authority to manage external chats |
| Add bot to external group via API | ❌ Blocked |
| Bot reads external group messages | ❌ Requires special external contact permissions |

### 9.3 Workaround

1. Create an **internal** group in your own tenant
2. Add the bot to it manually in Feishu UI
3. Invite members to the internal group

---

## 10. Troubleshooting: Issues & Solutions

### Issue 1: `99991672` — Permission Denied

**Symptom:**
```json
{
  "code": 99991672,
  "msg": "Access denied. One of the following scopes is required: [contact:user.id:readonly]"
}
```

**Cause:** API scope not granted.

**Fix:** Add the missing scope in Developer Console → Permission Management → republish → admin approval.

---

### Issue 2: `99991663` — Invalid Access Token

**Symptom:**
```json
{ "code": 99991663, "msg": "Invalid access token for authorization" }
```

**Causes:**
1. Token expired (tenant tokens last ~2 hours)
2. Wrong token type for the endpoint (e.g., using bot token for user-search API)
3. Another process refreshed the token, invalidating the old one

**Fix:**
- Refresh token: re-call `tenant_access_token/internal`
- For `/contact/v3/users/search`: use **user token**, not bot token

---

### Issue 3: `232033` — No Authority for External Chats

**Symptom:**
```json
{ "code": 232033, "msg": "The operator or invited bots does NOT have the authority to manage external chats" }
```

**Cause:** Trying to access a cross-tenant/external group.

**Fix:** Use internal groups only, or request `contact:external_contact` permissions (if available in your Feishu plan).

---

### Issue 4: Users Not Found in Search

**Symptom:** `contact +search-user` returns empty `users: []`

**Causes:**
1. Contact Data Scope is still restricted to specific members
2. User doesn't exist in the tenant
3. User is in an external tenant

**Fix:**
1. Check `GET /contact/v3/scopes` to verify contact data scope
2. Ensure admin approved **通讯录权限范围 → 全部成员**
3. Wait 5-10 minutes after approval for propagation

---

### Issue 5: "You are not in the event or event expired"

**Symptom:** Clicking calendar App Link shows this error.

**Cause:** Event created on bot calendar **without adding attendees via the separate attendee API**.

**Fix:**
1. Delete bot calendar event
2. Recreate event (on bot or user calendar)
3. **Call `POST .../attendees` separately** with `need_notification: true`
4. Send updated link to attendees

---

### Issue 6: Attendees Not Receiving Calendar Invitations

**Symptom:** Event created successfully, but no one sees it on their calendar.

**Cause:** Feishu **silently ignores** the `attendees` array inside the create-event request body. The event is created with zero attendees.

**Verification:**
```bash
lark-cli api GET /open-apis/calendar/v4/calendars/:calendar_id/events/:event_id/attendees --as bot
# Returns {"items": []} even though attendees were in the create body
```

**Fix:** Always add attendees in a **separate API call**:

```bash
# Step 1: Create event WITHOUT attendees in body
lark-cli api POST /open-apis/calendar/v4/calendars/:calendar_id/events --as bot \
  --data '{"summary": "Meeting", ...}'  # NO attendees field

# Step 2: Add attendees separately
lark-cli api POST /open-apis/calendar/v4/calendars/:calendar_id/events/:event_id/attendees --as bot \
  --data '{
    "attendees": [{"type": "user", "user_id": "ou_xxx"}],
    "need_notification": true
  }'
```

---

### Issue 7: `191002 — no calendar access_role`

**Symptom:**
```json
{ "code": 191002, "msg": "no calendar access_role" }
```

**Cause:** Bot tenant token does not have write permission to the target user's calendar.

**Fix:**
1. Fall back to creating the event on the **bot's primary calendar**.
2. Set the requester as `event_organizer` so their identity is preserved.
3. Add attendees via the separate attendee API (`POST .../attendees`).
4. Attendees will still receive invitations even though the event lives on the bot calendar.

To write directly to user calendars, you need either:
- A **user access token** (OAuth) from that user
- **Admin-level calendar permissions** granted to the app

---

### Issue 6: `99991679` — Action Privilege Required

**Symptom:**
```json
{ "code": 99991679, "msg": "Permission denied" }
```

**Cause:** User token lacks the specific scope (e.g., `contact:department.organize:readonly`).

**Fix:** Re-authorize lark-cli with the required scope:

```bash
lark-cli auth login --no-wait --scope "contact:department.organize:readonly"
# Then authorize in browser and complete with --device-code
```

---

## Appendix: Quick Reference Commands

```bash
# Check bot scopes
./feishu_permission_check.sh

# Check contact data scope
curl -H "Authorization: Bearer $TOKEN" \
  https://open.feishu.cn/open-apis/contact/v3/scopes

# Get tenant token
TOKEN=$(curl -s -X POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal \
  -H "Content-Type: application/json" \
  -d '{"app_id":"cli_a95e5e0371211bd3","app_secret":"j4sWTpFKIVrPafoh7mzCVnb1lrFXpylq"}' | \
  python3 -c "import sys,json;print(json.load(sys.stdin).get('tenant_access_token',''))")

# User auth for search
lark-cli auth login --no-wait --scope "contact:department.organize:readonly"
# ... authorize in browser ...
lark-cli auth login --device-code <code>

# Search user
lark-cli contact +search-user --query "Name"

# Create meeting on user calendar
lark-cli api POST /open-apis/calendar/v4/calendars/primary/events --as user \
  --data '{"summary":"Meeting","attendees":[{"type":"user","user_id":"ou_xxx"}]}'

# Semantier helper script (must provide requester)
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py create-meeting \
  --title "Meeting" \
  --start-time "2026-04-28 15:00" \
  --end-time "2026-04-28 15:30" \
  --attendee "ou_attendee_001" \
  --requester-open-id "ou_requester"

# Send group announcement
lark-cli im +messages-send --as bot --chat-id "oc_xxx" \
  --msg-type text --content '{"text":"Announcement"}'
```

---

## 11. Recurring Meetings

### 11.1 Overview

Feishu Calendar supports recurring events using **RRULE** (Recurrence Rule) strings, following the [iCalendar RFC 5545](https://datatracker.ietf.org/doc/html/rfc5545) standard.

When you create an event with a `recurrence` field, Feishu generates a **series** of event instances rather than a single event.

### 11.2 RRULE Format

```
FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20261231T235959Z
```

| Component | Meaning | Example |
|-----------|---------|---------|
| `FREQ` | Frequency | `DAILY`, `WEEKLY`, `MONTHLY` |
| `BYDAY` | Days of week | `MO,TU,WE,TH,FR` |
| `BYMONTHDAY` | Day of month | `1`, `15`, `-1` (last day) |
| `COUNT` | Number of occurrences | `10` |
| `UNTIL` | End date (UTC) | `20261231T235959Z` |
| `INTERVAL` | Skip intervals | `2` (every 2 weeks) |

### 11.3 Create a Weekly Recurring Meeting

```bash
START_TS=$(date -d '2026-04-28 10:00:00 CST' +%s)
END_TS=$(date -d '2026-04-28 11:00:00 CST' +%s)

lark-cli api POST /open-apis/calendar/v4/calendars/primary/events --as user \
  --data "{
    \"summary\": \"周例例会 / Weekly Standup\",
    \"description\": \"每周固定时间例会\",
    \"start_time\": {
      \"timestamp\": \"$START_TS\",
      \"timezone\": \"Asia/Shanghai\"
    },
    \"end_time\": {
      \"timestamp\": \"$END_TS\",
      \"timezone\": \"Asia/Shanghai\"
    },
    \"recurrence\": \"FREQ=WEEKLY;BYDAY=TU;UNTIL=20261231T235959Z\",
    \"attendees\": [
      {\"type\": \"user\", \"user_id\": \"ou_f2d55dbeddbcd43519c6efdf6d874712\"},
      {\"type\": \"user\", \"user_id\": \"ou_11d6838db5867f5784c9853296d7f6a1\"}
    ],
    \"vc_setting\": {
      \"vc_status\": \"no_vc\"
    }
  }"
```

**Response:**
```json
{
  "event": {
    "event_id": "abc123_0",
    "recurrence": "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261231T235959Z",
    "app_link": "https://applink.feishu.cn/client/calendar/event/detail?..."
  }
}
```

### 11.4 Common Recurrence Patterns

| Pattern | RRULE |
|---------|-------|
| Daily standup | `FREQ=DAILY;COUNT=30` |
| Weekly Tuesday | `FREQ=WEEKLY;BYDAY=TU;UNTIL=20261231T235959Z` |
| Bi-weekly Monday | `FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;UNTIL=20261231T235959Z` |
| Monthly 1st | `FREQ=MONTHLY;BYMONTHDAY=1;COUNT=12` |
| Monthly last Friday | `FREQ=MONTHLY;BYDAY=-1FR;COUNT=12` |
| Every weekday | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=20261231T235959Z` |

### 11.5 Reading Recurring Event Instances

To get all instances of a recurring series:

```bash
lark-cli api GET /open-apis/calendar/v4/calendars/primary/events/{event_id}/instances --as user \
  --params '{"start_time":"1700000000","end_time":"1800000000"}'
```

### 11.6 Updating Recurring Events

**Update entire series:**

```bash
lark-cli api PATCH /open-apis/calendar/v4/calendars/primary/events/{event_id} --as user \
  --data '{
    "summary": "Updated Weekly Standup",
    "description": "New agenda items added"
  }'
```

**Update a single instance (exception):**

Use the `original_time` parameter to target a specific occurrence:

```bash
lark-cli api PATCH /open-apis/calendar/v4/calendars/primary/events/{event_id}?original_time=1777946400 --as user \
  --data '{
    "summary": "Weekly Standup — Canceled This Week",
    "status": "cancelled"
  }'
```

### 11.7 Canceling Recurring Events

**Cancel entire series:**

```bash
lark-cli api DELETE /open-apis/calendar/v4/calendars/primary/events/{event_id} --as user \
  --data '{"need_notification": true}'
```

**Cancel single instance:**

```bash
lark-cli api DELETE /open-apis/calendar/v4/calendars/primary/events/{event_id}?original_time=1777946400 --as user \
  --data '{"need_notification": true}'
```

### 11.8 Important Notes

1. **Attendees receive one invite per series**, not per instance. Feishu handles the recurring logic internally.
2. **Modifying exceptions** creates a separate event instance detached from the series.
3. **Timezone matters:** The `UNTIL` timestamp must be in UTC (`Z` suffix), while event times use the specified timezone.
4. **User calendar required:** Same as single events — recurring events must be created on a **user's calendar** (`--as user`) to appear on attendees' personal calendars.
5. **No `EXDATE` support:** Feishu does not support explicit exclusion dates in RRULE. To skip a specific instance, create an exception and cancel it.

---

---

## 12. Interactive RSVP Cards

### 12.1 What Is an RSVP Card?

An **interactive RSVP card** is a Feishu message card with buttons that let users respond to meeting invitations **directly in chat** — without opening the Calendar app.

### 12.2 Why Use RSVP Cards

| Benefit | Description |
|---------|-------------|
| **Better UX** | Users don't leave the chat context |
| **Instant feedback** | Organizer sees accept/decline counts in real time |
| **Persistent state** | Card updates itself after each click |
| **Aggregated view** | Live counter: "3 accepted, 1 declined, 2 pending" |

### 12.3 How It Works

```
Bot sends card → User clicks button → Feishu sends webhook → Bot updates calendar + card
```

The semantier bot already has card action support enabled (`callback_type: websocket` in `callback_info`).

### 12.4 Send an RSVP Card

```bash
lark-cli im +messages-send --as bot \
  --chat-id "oc_747b1336232a45c7b7a8a2b14854cada" \
  --msg-type interactive \
  --content '{
    "config": {"wide_screen_mode": true},
    "header": {
      "title": {"tag": "plain_text", "content": "📅 Town Hall Meeting"},
      "template": "blue"
    },
    "elements": [
      {
        "tag": "div",
        "text": {
          "tag": "lark_md",
          "content": "**Time:** 2026-04-28 10:00-11:30\n**Location:** Conference Room A"
        }
      },
      {
        "tag": "action",
        "actions": [
          {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "✅ Accept"},
            "type": "primary",
            "value": {"action": "rsvp_accept", "event_id": "f5cabef3-6cdc-4285-a0d8-c7773531cb05_0"}
          },
          {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "⚠️ Tentative"},
            "type": "default",
            "value": {"action": "rsvp_tentative", "event_id": "f5cabef3-6cdc-4285-a0d8-c7773531cb05_0"}
          },
          {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "❌ Decline"},
            "type": "danger",
            "value": {"action": "rsvp_decline", "event_id": "f5cabef3-6cdc-4285-a0d8-c7773531cb05_0"}
          }
        ]
      },
      {
        "tag": "div",
        "text": {
          "tag": "lark_md",
          "content": "**Responses:**\n✅ chris han\n⬜ Amy Q"
        }
      }
    ]
  }'
```

### 12.5 Handle Button Clicks

When a user clicks a button, Feishu sends a `card.action.trigger` event:

```json
{
  "open_id": "ou_f2d55dbeddbcd43519c6efdf6d874712",
  "open_message_id": "om_xxx",
  "token": "challenge-token",
  "action": {
    "value": {
      "action": "rsvp_accept",
      "event_id": "f5cabef3-6cdc-4285-a0d8-c7773531cb05_0"
    }
  }
}
```


**Backend handler (production-ready):**

```python
"""Feishu Card RSVP + Time Slot Negotiation Handler"""
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class AttendeeResponse:
    user_id: str
    user_name: str
    rsvp: str = "pending"
    preferred_slots: List[str] = field(default_factory=list)
    responded_at: Optional[str] = None


@dataclass
class MeetingPoll:
    event_id: str
    message_id: str
    chat_id: str
    proposed_slots: List[str]
    responses: Dict[str, AttendeeResponse] = field(default_factory=dict)
    status: str = "polling"


class FeishuRSVPManager:
    def __init__(self, calendar_client, message_client):
        self.calendar = calendar_client
        self.message = message_client
        self._polls: Dict[str, MeetingPoll] = {}
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def handle_card_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = payload.get("open_id", "")
        user_name = payload.get("user_name", "Unknown")
        message_id = payload.get("open_message_id", "")
        action_value = payload.get("action", {}).get("value", {})
        action_type = action_value.get("action", "")
        event_id = action_value.get("event_id", "")

        async with self._locks[event_id]:
            if action_type.startswith("rsvp_"):
                return await self._handle_rsvp(
                    event_id, user_id, user_name, message_id,
                    action_type.replace("rsvp_", ""),
                )
            elif action_type == "vote_slot":
                return await self._handle_slot_vote(
                    event_id, user_id, user_name, message_id,
                    action_value.get("slot", ""),
                )
            elif action_type == "submit_availability":
                form_data = action_value.get("form", {})
                return await self._handle_availability_submission(
                    event_id, user_id, user_name, message_id,
                    form_data.get("slots", ""),
                )
            elif action_type == "confirm_slot":
                return await self._handle_final_confirmation(
                    event_id, message_id, action_value.get("slot", ""),
                )
        return {"toast": {"type": "info", "content": "Action processed"}}

    async def _handle_rsvp(self, event_id, user_id, user_name, message_id, rsvp):
        await self.calendar.update_attendee_rsvp(event_id, user_id, rsvp)
        poll = self._polls.setdefault(event_id, MeetingPoll(
            event_id=event_id, message_id=message_id, chat_id="", proposed_slots=[]
        ))
        poll.responses.setdefault(user_id, AttendeeResponse(user_id, user_name))
        poll.responses[user_id].rsvp = rsvp
        poll.responses[user_id].responded_at = datetime.now().isoformat()
        await self.message.patch_card(message_id, self._build_rsvp_card(poll))
        status_text = {"accept": "Accepted ✅", "tentative": "Maybe ⚠️", "decline": "Declined ❌"}.get(rsvp, "Updated")
        return {"toast": {"type": "success", "content": status_text}}

    async def _handle_slot_vote(self, event_id, user_id, user_name, message_id, slot):
        poll = self._polls.get(event_id)
        if not poll:
            return {"toast": {"type": "error", "content": "Poll not found"}}
        poll.responses.setdefault(user_id, AttendeeResponse(user_id, user_name))
        current = poll.responses[user_id].preferred_slots
        if slot in current:
            current.remove(slot)
        else:
            current.append(slot)
        consensus = self._find_consensus(poll)
        if consensus and poll.status == "polling":
            poll.status = "negotiating"
            card = self._build_consensus_card(poll, consensus)
        else:
            card = self._build_slot_poll_card(poll)
        await self.message.patch_card(message_id, card)
        return {"toast": {"type": "success", "content": f"Consensus: {consensus}" if consensus else f"Voted: {slot}"}}

    async def _handle_availability_submission(self, event_id, user_id, user_name, message_id, slots_text):
        poll = self._polls.get(event_id)
        if not poll:
            return {"toast": {"type": "error", "content": "Poll not found"}}
        poll.responses.setdefault(user_id, AttendeeResponse(user_id, user_name))
        poll.responses[user_id].preferred_slots = self._parse_free_text_slots(slots_text)
        all_responded = len(poll.responses) >= self._expected_attendee_count(event_id)
        if all_responded:
            best = await self._negotiate_time(poll)
            if best:
                poll.status = "negotiating"
                await self.message.patch_card(message_id, self._build_consensus_card(poll, best))
                return {"toast": {"type": "success", "content": f"Best time: {best}"}}
        await self.message.patch_card(message_id, self._build_availability_card(poll, len(poll.responses)))
        return {"toast": {"type": "success", "content": "Availability recorded"}}

    async def _handle_final_confirmation(self, event_id, message_id, slot):
        poll = self._polls.get(event_id)
        if poll:
            await self.calendar.update_event_time(event_id, slot)
            poll.status = "confirmed"
            await self.message.patch_card(message_id, self._build_confirmed_card(poll, slot))
        return {"toast": {"type": "success", "content": "Meeting confirmed!"}}

    def _find_consensus(self, poll: MeetingPoll) -> Optional[str]:
        counts: Dict[str, int] = defaultdict(int)
        for r in poll.responses.values():
            for s in r.preferred_slots:
                counts[s] += 1
        total = len(poll.responses)
        for slot, count in sorted(counts.items(), key=lambda x: -x[1]):
            if count == total:
                return slot
        return max(counts.items(), key=lambda x: x[1])[0] if counts else None

    async def _negotiate_time(self, poll: MeetingPoll) -> Optional[str]:
        all_sets = [set(r.preferred_slots) for r in poll.responses.values() if r.preferred_slots]
        if all_sets:
            intersection = all_sets[0].intersection(*all_sets[1:])
            if intersection:
                return sorted(intersection)[0]
        return self._find_consensus(poll)

    def _parse_free_text_slots(self, text: str) -> List[str]:
        text = text.lower().strip()
        slots = []
        days = [("mon", "周一", "Mon"), ("tue", "周二", "Tue"), ("wed", "周三", "Wed"),
                ("thu", "周四", "Thu"), ("fri", "周五", "Fri")]
        for en, zh, label in days:
            if en in text or zh in text:
                slots.append(f"{label} 14:00")
        return slots or [text[:50]]

    def _expected_attendee_count(self, event_id: str) -> int:
        return 2  # Fetch from Calendar API in production

    # --- Card builders ---
    def _build_rsvp_card(self, poll: MeetingPoll) -> Dict[str, Any]:
        a = sum(1 for r in poll.responses.values() if r.rsvp == "accept")
        t = sum(1 for r in poll.responses.values() if r.rsvp == "tentative")
        d = sum(1 for r in poll.responses.values() if r.rsvp == "decline")
        return {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "📅 Meeting RSVP"}, "template": "blue"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**Responses:** {a} ✅ | {t} ⚠️ | {d} ❌"}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "✅ Accept"}, "type": "primary", "value": {"action": "rsvp_accept", "event_id": poll.event_id}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "⚠️ Tentative"}, "type": "default", "value": {"action": "rsvp_tentative", "event_id": poll.event_id}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "❌ Decline"}, "type": "danger", "value": {"action": "rsvp_decline", "event_id": poll.event_id}},
                ]}
            ]
        }

    def _build_slot_poll_card(self, poll: MeetingPoll) -> Dict[str, Any]:
        counts: Dict[str, int] = defaultdict(int)
        for r in poll.responses.values():
            for s in r.preferred_slots:
                counts[s] += 1
        lines = "\n".join([f"- {s}: {counts.get(s, 0)} votes" for s in poll.proposed_slots])
        actions = [{"tag": "button", "text": {"tag": "plain_text", "content": f"Vote: {s}"}, "type": "default", "value": {"action": "vote_slot", "event_id": poll.event_id, "slot": s}} for s in poll.proposed_slots]
        return {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "⏰ Time Slot Poll"}, "template": "orange"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**Vote for available slots:**\n{lines}"}},
                {"tag": "action", "actions": actions}
            ]
        }

    def _build_consensus_card(self, poll: MeetingPoll, slot: str) -> Dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "✅ Time Proposed"}, "template": "green"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**Best time:** {slot}\n\nConfirm to finalize."}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "Confirm This Time"}, "type": "primary", "value": {"action": "confirm_slot", "event_id": poll.event_id, "slot": slot}}
                ]}
            ]
        }

    def _build_availability_card(self, poll: MeetingPoll, awaiting: int) -> Dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "📝 Share Your Availability"}, "template": "blue"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"{awaiting} people responded.\nExample: \"Mon 2pm, Wed morning\""}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "Submit Availability"}, "type": "primary", "value": {"action": "submit_availability", "event_id": poll.event_id}}
                ]}
            ]
        }

    def _build_confirmed_card(self, poll: MeetingPoll, slot: str) -> Dict[str, Any]:
        return {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "📅 Meeting Confirmed"}, "template": "green"},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**Time:** {slot}\n**Status:** Confirmed ✅"}}
            ]
        }
```

### 12.6 Update Calendar RSVP via API

```bash
lark-cli api PATCH /open-apis/calendar/v4/calendars/primary/events/{event_id}/attendees/{attendee_id} --as user \
  --data '{"rsvp_status": "accept"}'
```

### 12.7 Update the Card After Click

```bash
lark-cli api PATCH /open-apis/im/v1/messages/{message_id} --as bot \
  --data '{
    "content": "{\"config\":{...},\"elements\":[...updated response list...]}"
  }'
```

### 12.8 RSVP Card Limitations

| Issue | Workaround |
|-------|-----------|
| Requires `cardkit:card:write` scope | ✅ Already granted to semantier |
| Webhook must be running | Semantier uses WebSocket mode (`FEISHU_CONNECTION_MODE=websocket`) |
| Cannot directly modify calendar from card without backend | Bot must handle callback and call Calendar API |
| Duplicate clicks possible | Implement idempotency (deduplicate by `open_id` + `action` + `timestamp`) |
| Card patch rate limits | Batch updates or debounce rapid clicks |

### 12.9 RSVP + Recurring Meetings

For recurring meetings, RSVP should target the **series** (not individual instances) unless the user is responding to a specific occurrence:

```json
{
  "value": {
    "action": "rsvp_accept",
    "event_id": "abc123_0",
    "original_time": null
  }
}
```

To RSVP for a **single instance only**, include `original_time`:

```json
{
  "value": {
    "action": "rsvp_decline",
    "event_id": "abc123_0",
    "original_time": "1777946400"
  }
}
```

---

## 13. Time Slot Negotiation

### 13.1 Concept

Instead of proposing a fixed meeting time, the bot can **collect availability** from all attendees and **negotiate** the optimal time automatically.

**Two approaches:**

| Approach | When to Use | User Input |
|----------|-------------|------------|
| **Predefined Slots** (voting) | Organizer has 2-4 specific options in mind | Click buttons for available slots |
| **Free-Text Availability** | Flexible timing, needs open-ended input | Type natural language (e.g., "Mon 2pm, Wed morning") |

### 13.2 Predefined Slot Voting

Bot sends a card with time options. Users vote for all slots they can attend. Bot finds the **intersection** (slot with most votes).

```bash
lark-cli im +messages-send --as bot \
  --chat-id "oc_747b1336232a45c7b7a8a2b14854cada" \
  --msg-type interactive \
  --content '{
    "config": {"wide_screen_mode": true},
    "header": {"title": {"tag": "plain_text", "content": "⏰ Pick Your Available Slots"}, "template": "orange"},
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md", "content": "Click **all** times you are available. We will pick the one that works for everyone."}},
      {"tag": "action", "actions": [
        {"tag": "button", "text": {"tag": "plain_text", "content": "Tue 10:00"}, "type": "default", "value": {"action": "vote_slot", "event_id": "evt_123", "slot": "Tue 10:00"}},
        {"tag": "button", "text": {"tag": "plain_text", "content": "Tue 14:00"}, "type": "default", "value": {"action": "vote_slot", "event_id": "evt_123", "slot": "Tue 14:00"}},
        {"tag": "button", "text": {"tag": "plain_text", "content": "Wed 10:00"}, "type": "default", "value": {"action": "vote_slot", "event_id": "evt_123", "slot": "Wed 10:00"}},
        {"tag": "button", "text": {"tag": "plain_text", "content": "Wed 14:00"}, "type": "default", "value": {"action": "vote_slot", "event_id": "evt_123", "slot": "Wed 14:00"}}
      ]}
    ]
  }'
```

**Negotiation logic:**

```python
def find_best_slot(poll):
    # Strategy 1: Exact intersection (everyone available)
    all_slots = [set(r.preferred_slots) for r in poll.responses.values()]
    intersection = all_slots[0].intersection(*all_slots[1:])
    if intersection:
        return sorted(intersection)[0]  # Earliest common slot
    
    # Strategy 2: Majority vote
    counts = defaultdict(int)
    for r in poll.responses.values():
        for s in r.preferred_slots:
            counts[s] += 1
    return max(counts.items(), key=lambda x: x[1])[0]
```

### 13.3 Free-Text Availability

Users type their availability in natural language. The bot parses it and negotiates.

```bash
lark-cli im +messages-send --as bot \
  --chat-id "oc_747b1336232a45c7b7a8a2b14854cada" \
  --msg-type interactive \
  --content '{
    "config": {"wide_screen_mode": true},
    "header": {"title": {"tag": "plain_text", "content": "📝 When Are You Free?"}, "template": "blue"},
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md", "content": "Reply with your availability this week.\n\n**Examples:**\n- \"Mon 2pm, Wed morning, Fri after 3pm\"\n- \"Tuesday or Thursday afternoons\"\n- \"Any day except Wednesday\""}},
      {"tag": "action", "actions": [
        {"tag": "button", "text": {"tag": "plain_text", "content": "Submit My Availability"}, "type": "primary", "value": {"action": "submit_availability", "event_id": "evt_123"}}
      ]}
    ]
  }'
```

**Parsing free text:**

```python
def parse_availability(text: str) -> List[str]:
    """Parse natural language availability into structured slots."""
    text = text.lower()
    slots = []
    
    # Simple keyword matching (replace with LLM for production)
    day_map = {
        "mon": "Mon", "monday": "Mon", "周一": "Mon",
        "tue": "Tue", "tuesday": "Tue", "周二": "Tue",
        "wed": "Wed", "wednesday": "Wed", "周三": "Wed",
        "thu": "Thu", "thursday": "Thu", "周四": "Thu",
        "fri": "Fri", "friday": "Fri", "周五": "Fri",
    }
    
    for keyword, label in day_map.items():
        if keyword in text:
            if "morning" in text or "上午" in text:
                slots.append(f"{label} 09:00")
            elif "afternoon" in text or "下午" in text:
                slots.append(f"{label} 14:00")
            elif "evening" in text or "晚上" in text:
                slots.append(f"{label} 18:00")
            else:
                slots.append(f"{label} 14:00")  # Default
    
    return slots or [text[:50]]  # Fallback: store raw text
```

**Production upgrade:** Replace `parse_availability` with an LLM call:

```python
async def parse_with_llm(text: str) -> List[str]:
    prompt = f"Extract available time slots from: '{text}'. Return JSON array like ['Mon 14:00', 'Wed 09:00']."
    result = await llm_chat_complete(prompt)
    return json.loads(result)
```

### 13.4 Full Negotiation Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Bot sends  │────▶│ Users click/ │────▶│ Bot stores  │
│  time poll  │     │ type replies │     │ responses   │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                 │
                          ┌──────────────────────┘
                          ▼
                   ┌─────────────┐
                   │ All voted?  │────No────▶ Wait for more
                   └──────┬──────┘
                          │ Yes
                          ▼
                   ┌─────────────┐
                   │ Find best   │
                   │ slot (agent)│
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │ Send consensus│
                   │ card for confirm│
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │ Organizer   │
                   │ confirms    │
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │ Create event│
                   │ on calendar │
                   └─────────────┘
```

### 13.5 Consensus Card

After negotiation, bot sends a confirmation card:

```bash
lark-cli im +messages-send --as bot \
  --chat-id "oc_747b1336232a45c7b7a8a2b14854cada" \
  --msg-type interactive \
  --content '{
    "config": {"wide_screen_mode": true},
    "header": {"title": {"tag": "plain_text", "content": "✅ Meeting Time Confirmed"}, "template": "green"},
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md", "content": "**Best time for everyone:**\n🗓️ Tuesday, April 28 at 14:00\n\n✅ chris han\n✅ Amy Q\n⬜ Henry wang (awaiting)"}},
      {"tag": "action", "actions": [
        {"tag": "button", "text": {"tag": "plain_text", "content": "Create Calendar Event"}, "type": "primary", "value": {"action": "confirm_slot", "event_id": "evt_123", "slot": "Tue 14:00"}},
        {"tag": "button", "text": {"tag": "plain_text", "content": "Suggest Alternative"}, "type": "default", "value": {"action": "renegotiate", "event_id": "evt_123"}}
      ]}
    ]
  }'
```

### 13.6 Limitations

| Issue | Workaround |
|-------|-----------|
| Users may not respond | Set a deadline; auto-pick best slot after timeout |
| No common slot found | Suggest least-bad option or split into two meetings |
| Free-text parsing errors | Use LLM for production parsing; fallback to manual review |
| Timezone ambiguity | Always specify timezone (e.g., "Asia/Shanghai") |
| Feishu cards don't support multi-select natively | Use toggle buttons (click to vote/unvote) |

---

## Summary

| Goal | Right Way | Wrong Way |
|------|-----------|-----------|
| Create visible meeting | Bot calendar + separate attendee API + `need_notification` | Put `attendees` in create-event body (silently ignored) |
| Search users | User token + `contact:user:search` | Bot token |
| Invite all members | Expand Contact Data Scope to "All members" | Only add API scopes |
| Access group members | Internal groups | External/cross-tenant groups |
| Send announcements | Bot message to chat | Calendar invite alone |
| Recurring meetings | RRULE on user calendar | Bot calendar (no sync) |
| RSVP tracking | Interactive card + webhook | Text-only message |
| Time negotiation | Slot voting or free-text + agent logic | Fixed time with no feedback |
| Set organizer identity | `event_organizer` field in create body | Let it default to bot identity |
| Participant list visibility | `attendee_ability: "can_see_others"` | Default hidden |
| Get user calendar ID | `primarys` API with `user_ids` | `primary` API (returns bot's calendar) |
