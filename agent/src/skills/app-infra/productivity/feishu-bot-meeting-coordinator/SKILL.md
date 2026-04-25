---
name: feishu-bot-meeting-coordinator
description: >
  Coordinate Feishu bot-assisted contact search and meeting scheduling for
  workspace users. Use this skill when the Semantier backend is configured to
  run multi-round attendee availability negotiation, then create the final
  calendar events on participant calendars with initiator ownership semantics,
  and deliver invitations.
version: 1.0.0
author: Semantier
license: MIT
tags:
  - feishu
  - calendar
  - meetings
  - contacts
triggers:
  - schedule a feishu meeting
  - find feishu contacts
  - invite contacts in feishu
  - create feishu meeting
  - search feishu contact
  - 创建飞书会议
  - 安排飞书会议
  - 搜索飞书联系人
  - 飞书会议邀请
metadata:
  hermes:
    tags: [feishu, calendar, meetings, contacts]
    config:
      - key: feishu.bot.identity
        description: Human-readable organizer identity for the installed Feishu bot
        default: semantier
        prompt: Feishu bot organizer identity
      - key: feishu.bot.timezone
        description: Default timezone to use when the user does not specify one
        default: Asia/Shanghai
        prompt: Default timezone for Feishu meetings
      - key: feishu.bot.contact_scope
        description: Expected contact visibility model for the bot's searchable contacts
        default: contacts-added-to-bot
        prompt: Bot contact visibility mode
---

# Feishu Bot Meeting Coordinator

## Purpose

Use this skill to coordinate a Feishu bot that can:

- search the bot's visible contact list
- run multi-round availability negotiation with each attendee
- create calendar meetings on each participant calendar after agreement
- invite user-selected contacts to the meeting

This skill is for the direct Feishu bot/API path.

## Runtime Contract: Script Materialization

**IMPORTANT**: This skill follows the Semantier **Deterministic File Operations** and **Per-Task Sandboxing** architecture laws (see [semantier-architecture-laws](../../../../.github/skills/semantier-architecture-laws/SKILL.md)).

### What You Don't Do
- Do NOT reference absolute system paths like `/home/chris/repo/semantier/agent/src/skills/...`
- Do NOT use `skill_view(...)` to manually load script code into context
- Do NOT use hardcoded paths in terminal commands

### What the Wrapper Layer Does (Automatically)
The `/agent` wrapper layer automatically:

1. **Detects** that this skill execution needs the helper script
2. **Materializes** the shared script from `agent/src/skills/app-infra/productivity/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py` into the task sandbox
3. **Exposes** the script at a sandbox-relative path like `.scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py`
4. **Cleans up** the script when the task completes (no leftovers)

This ensures:
- ✅ No sandbox escape attempts
- ✅ No cross-task interference (each task gets its own copy)
- ✅ Works across all deployment models (local, Docker, serverless)

## Execution Surface

### Loading the Helper

The wrapper layer automatically injects the helper script into your workspace. **You reference it as a relative path in the task sandbox**, not as a system path.

**Example usage in Python/bash**:

```bash
# Terminal command (wrapper materializes to task sandbox automatically)
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py search-chats --query "管理层群"
```

**Credentials and Config**:
- Credentials are automatically loaded from the agent installation's `.env` file at runtime
- Workspace config (timezone, identity) is read from `.hermes/config.yaml` by the script
- You do NOT ask users to verify environment variables or provide secrets in chat

### Helper API Surface

The materialized script provides:

```python
# search-chats: Find contact groups by keyword
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  search-chats --query "管理层群" --limit 5

# search-contacts: Find individual contacts by name or email
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  search-contacts --query "张三" --limit 10

# get-chat-members: Retrieve all members of a contact group
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  get-chat-members --chat-id "<chat_id>"

# propose-meeting-slots: Propose time slots and collect availability
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  propose-meeting-slots --attendees '["<id1>", "<id2>"]' \
    --title "项目汇报会" --slots '[{"start": "2026-04-28T10:00:00", ...}]'

# create-meeting: Create calendar event after agreement
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  create-meeting --title "项目汇报会" \
    --attendees '["<id1>", "<id2>"]' \
    --start "2026-04-28T10:00:00" --duration-minutes 30

# send-invitations: Send invitation messages to attendees
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  send-invitations --meeting-id "<meeting_id>" \
    --attendees '["<id1>", "<id2>"]' --message "会议已创建，请准时参加"
```

## Installed Skill Config

When this skill is installed into a workspace, use the configured values as follows:

- `feishu.bot.identity`: treat as the organizer identity to reference in summaries and confirmations; use `semantier` as the default organizer identity for Feishu functions
- `feishu.bot.timezone`: use as the default timezone for proposed meeting times
- `feishu.bot.contact_scope`: assume this describes which contacts are expected to be discoverable by the bot

## Operating Rules

1. Use the Feishu bot identity `semantier` as the organizer identity for contact search, meeting creation, and meeting summaries unless an explicit workspace config override is provided.
2. **MANDATORY**: When any required meeting field is missing, you MUST emit the `a2ui` `schema_form` block defined in the **Missing Input A2UI Contract** section below. A free-form markdown bullet list asking for the same fields is NEVER acceptable — even when reading the skill for the first time.
3. Resolve attendees through the materialized `feishu_bot_api.py` script rather than guessing account identifiers.
4. Confirm ambiguous contact matches before creating the meeting.
5. Run attendee negotiation rounds until all attendees agree on one slot or rounds are exhausted.
6. After agreement, create meeting items on each participant calendar using the same agreed slot and attendee list.
7. Treat the request initiator as the meeting owner identity in summaries and final outputs.

## Implementation Guidelines: Using the Materialized Script

### Step 1: Search for Contacts or Groups

```bash
# Search for a contact group (if user specifies "管理层群")
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  search-chats --query "管理层群" --limit 5

# Expected output (JSON):
# {
#   "status": "success",
#   "results": [
#     {"id": "oc_abc123", "name": "管理层群", "member_count": 5}
#   ]
# }
```

### Step 2: Get Group Members (if applicable)

```bash
# Retrieve members of the contact group
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  get-chat-members --chat-id "oc_abc123"

# Expected output (JSON):
# {
#   "status": "success",
#   "members": [
#     {"id": "ou_xyz123", "name": "张三", "email": "zhangsan@example.com"}
#   ]
# }
```

### Step 3: Propose Meeting Slots

```bash
# Propose available time slots for attendees to choose from
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  propose-meeting-slots \
    --attendees '["ou_xyz123", "ou_abc456"]' \
    --title "项目汇报会" \
    --slots '[
      {"start": "2026-04-28T09:00:00+08:00", "end": "2026-04-28T10:00:00+08:00"},
      {"start": "2026-04-28T14:00:00+08:00", "end": "2026-04-28T15:00:00+08:00"}
    ]'

# Expected output (JSON):
# {
#   "status": "success",
#   "proposal_id": "prop_123abc",
#   "message_ids": ["msg_1", "msg_2"],
#   "pending_responses": 2
# }
```

### Step 4: Create Meeting After Agreement

```bash
# Create the final calendar event (after all attendees agree)
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  create-meeting \
    --title "项目汇报会" \
    --description "按照既定时间进行项目进度汇报" \
    --start "2026-04-28T10:00:00+08:00" \
    --duration-minutes 30 \
    --attendees '["ou_xyz123", "ou_abc456"]' \
    --organizer "semantier"

# Expected output (JSON):
# {
#   "status": "success",
#   "meeting_id": "event_123xyz",
#   "calendar_links": [
#     "https://feishu.example.com/calendar/event/event_123xyz"
#   ]
# }
```

### Step 5: Send Invitations

```bash
# Send invitation messages to all attendees
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  send-invitations \
    --meeting-id "event_123xyz" \
    --attendees '["ou_xyz123", "ou_abc456"]' \
    --message "会议已创建，请准时参加"

# Expected output (JSON):
# {
#   "status": "success",
#   "sent_count": 2,
#   "failed": []
# }
```

## Missing Input A2UI Contract

When required meeting fields are missing, emit this schema form (do NOT use markdown lists):

```json
{
  "type": "schema_form",
  "title": "补全会议信息",
  "description": "请提供以下信息以完成会议安排",
  "fields": [
    {
      "name": "title",
      "label": "会议主题",
      "type": "text",
      "required": true,
      "placeholder": "例如：项目汇报会",
      "help": "会议的标题和目的"
    },
    {
      "name": "time",
      "label": "会议时间",
      "type": "datetime",
      "required": true,
      "placeholder": "2026-04-28T10:00",
      "help": "建议时间 (ISO 8601 格式)"
    },
    {
      "name": "duration",
      "label": "会议时长（分钟）",
      "type": "number",
      "required": true,
      "placeholder": "30",
      "help": "会议预期时长"
    },
    {
      "name": "attendees",
      "label": "参会人员",
      "type": "multiselect",
      "required": true,
      "placeholder": "选择参会人员",
      "help": "从联系人中选择参与者",
      "options": []
    }
  ]
}
```
8. Send final invitation notifications to each resolved attendee after event creation.
9. Summarize invitees, timezone, and schedule before final confirmation when the user request is ambiguous.
10. Treat app secrets, user tokens, and webhook secrets as backend-owned secrets. Never ask the user to paste them into chat or store them in skill config.
11. If the attendee expression contains a group phrase (for example `管理层群`, `管理层群里的所有人`), you MUST resolve group members via Feishu chat/member APIs before asking the user for manual names.

## Helper Entry Points

- Contact search CLI: `python scripts/feishu_bot_api.py search-contacts --query "Amy Q" --limit 5`
- Meeting creation CLI: `python scripts/feishu_bot_api.py create-meeting --title "项目同步" --start-time "2026-04-24 15:40" --end-time "2026-04-24 16:10" --attendee "Chris Han" --attendee "Amy Q"`
- Start negotiation CLI: `python scripts/feishu_bot_api.py start-negotiation --title "项目同步" --initiator-open-id "ou_xxx" --duration-minutes 30 --attendee-open-id "ou_a" --attendee-open-id "ou_b" --candidate-slot "2026-04-24 15:40" --candidate-slot "2026-04-24 16:40"`
- Submit response CLI: `python scripts/feishu_bot_api.py submit-response --state-json '{...}' --attendee-open-id "ou_a" --accepted-slot "2026-04-24 15:40"`
- Finalize CLI: `python scripts/feishu_bot_api.py finalize-negotiation --state-json '{...}' --description "讨论项目进展"`
- Python API: import `search_contacts(...)`, `start_negotiation(...)`, `submit_attendee_response(...)`, `finalize_negotiation_and_create_meeting(...)`, and `create_meeting(...)` from `scripts/feishu_bot_api.py`.


## Missing Input A2UI Contract

> **MANDATORY OUTPUT FORMAT**: This is a hard constraint. When any required meeting field (title, time, duration, attendees) is missing, the only permitted response format is the `a2ui` `schema_form` block below followed by one short plain sentence. A markdown bullet list, numbered list, or prose request for the same information is a contract violation.

When the user wants to schedule a meeting but required fields are missing, emit exactly one fenced `a2ui` JSON block using `schema_form`, then add one short plain-language sentence below it. Do not precede it with a markdown list of questions.

Use this schema shape exactly for meeting scheduling:

```a2ui
{
  "version": "1.0",
  "root": {
    "component": "schema_form",
    "props": {
      "title": "请补充飞书会议信息",
      "submitLabel": "提交会议信息",
      "followUp": "请根据以上会议信息继续搜索联系人并创建飞书会议。",
      "fields": [
        {
          "key": "meeting_title",
          "label": "会议主题",
          "type": "text",
          "required": true,
          "placeholder": "例如：项目周会"
        },
        {
          "key": "meeting_time",
          "label": "会议时间",
          "type": "text",
          "required": true,
          "placeholder": "例如：今天下午 3:40 或 2026-04-24 15:40"
        },
        {
          "key": "duration_value",
          "label": "会议时长数值",
          "type": "number",
          "required": true,
          "placeholder": "例如：30"
        },
        {
          "key": "duration_unit",
          "label": "会议时长单位",
          "type": "select",
          "required": true,
          "default": "分钟",
          "options": [
            { "label": "分钟", "value": "分钟" },
            { "label": "小时", "value": "小时" }
          ],
          "placeholder": "请选择时长单位"
        },
        {
          "key": "attendees",
          "label": "参会人员",
          "type": "text",
          "required": true,
          "placeholder": "例如：张三, Henry Wang"
        },
        {
          "key": "meeting_description",
          "label": "会议描述",
          "type": "textarea",
          "required": false,
          "placeholder": "可选：补充会议背景、议程或备注"
        }
      ]
    }
  }
}
```

Rules for this schema:

- Never include meta-instruction labels such as `根据技能说明`, `我需要了解以下信息`, or `我来帮您安排会议` as form fields.
- Never merge `会议时长` into a single hardcoded hour assumption. Always collect `duration_value` and `duration_unit` separately.
- `meeting_description` is optional and must remain `required: false`.
- If the user already supplied some fields, keep the same schema keys and only ask for the missing ones.
- If the attendee names might be ambiguous, still collect them in `attendees` first; resolve them through backend contact search after submit.

## Response Shape

For contact search results, prefer compact tables with columns for display name, Feishu identifier, and confidence or matching note.

For meeting creation, return:

- organizer identity
- initiator identity
- meeting title
- start and end time with timezone
- invited contacts
- any contacts that could not be resolved

## Failure Handling

 If no matching contacts are found, report that clearly and ask for a refined name, department, or alias.
 If multiple contacts match, present the candidates and ask the user to choose.
 If the calendar operation fails, preserve the resolved attendee candidates so the user does not need to repeat them.
 If backend Feishu bot/API capability is unavailable in the current runtime, state that explicitly and ask the user whether to continue later after backend recovery or switch to a manual scheduling fallback.