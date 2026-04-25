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

**IMPORTANT**: This skill follows the Semantier **Deterministic File Operations** and **Per-Task Sandboxing** architecture laws (see [semantier-architecture-laws](../../../../../../.github/skills/semantier-architecture-laws/SKILL.md)).

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

Before attempting contact search or meeting creation, load the helper code with `skill_view(name="feishu-bot-meeting-coordinator", file_path="scripts/feishu_bot_api.py")`.

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

# get-chat-members: Retrieve all members of a contact group
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  get-chat-members --chat-id "oc_abc123"

# search-contacts: Find individual contacts by name or email
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  search-contacts --query "张三" --limit 10

# start-negotiation: Start a multi-round availability negotiation
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  start-negotiation --title "项目汇报会" \
    --initiator-open-id "ou_owner" --duration-minutes 30 \
    --attendee-open-id "ou_a" --attendee-open-id "ou_b" \
    --candidate-slot "2026-04-28 15:00" --candidate-slot "2026-04-28 15:30"

# submit-response: Record an attendee response for the current round
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  submit-response --state-json '<state-json>' --attendee-open-id "ou_a" \
    --accepted-slot "2026-04-28 15:00"

# finalize-negotiation: Create meetings after a slot is agreed
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  finalize-negotiation --state-json '<state-json>' --description "项目进度汇报"

# create-meeting: Create calendar event after agreement
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  create-meeting --title "项目汇报会" \
    --start-time "2026-04-28 15:00" --end-time "2026-04-28 15:30" \
    --attendee "张三" --attendee "李四" --description "项目进度汇报"
```

## Installed Skill Config

When this skill is installed into a workspace, use the configured values as follows:

- `feishu.bot.identity`: treat as the organizer identity to reference in summaries and confirmations; use `semantier` as the default organizer identity for Feishu functions
- `feishu.bot.timezone`: use as the default timezone for proposed meeting times
- `feishu.bot.contact_scope`: assume this describes which contacts are expected to be discoverable by the bot

## Operating Rules

1. Use the Feishu bot identity `semantier` as the organizer identity for contact search, meeting creation, and meeting summaries unless an explicit workspace config override is provided.
1a. If the user explicitly designates an organizer (for example: `组织者是 X` or `organizer is X`), you MAY use that designated organizer instead of the default session owner.
1b. If `organizer` and `initiator` are not the same person, you MUST obtain explicit approval from the designated organizer before running `create-meeting` or `finalize-negotiation`.
1c. Approval must be explicit and attributable to the designated organizer (clear yes/approve intent). If approval is missing or ambiguous, do not create events.
2. **MANDATORY**: When any required meeting field is missing, you MUST emit the `a2ui` `schema_form` block defined in the **Missing Input A2UI Contract** section below. A free-form markdown bullet list asking for the same fields is NEVER acceptable — even when reading the skill for the first time.
2a. When the agent is not certain about any required meeting field, it must ask the user to clarify via that form. Do not silently assume a default duration, attendee list, or other required value.
2b. Before creating an event, if any parameter is inferred/defaulted (for example duration, timezone, description, or selected organizer/initiator), you MUST show a pre-create review `schema_form` with those default values and ask whether to edit or approve.
3. Resolve attendees through the materialized `feishu_bot_api.py` script rather than guessing account identifiers.
4. Confirm ambiguous contact matches before creating the meeting.
5. Run attendee negotiation rounds until all attendees agree on one slot or rounds are exhausted.
6. After agreement, create meeting items on each participant calendar using the same agreed slot and attendee list.
7. Treat the request initiator as the meeting owner identity in summaries and final outputs.
7a. If organizer override is used, include both identities explicitly in confirmations: organizer identity and initiator identity.
7b. Never execute create-event calls when organizer approval is still pending.

## Implementation Guidelines: Using the Materialized Script

### Step 1: Search for Contacts or Groups

```bash
# Search for a contact group (if user specifies "管理层群")
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  search-chats --query "管理层群" --limit 5

# Expected output (JSON):
# {
#   "ok": true,
#   "result": {
#     "query": "管理层群",
#     "candidates": [
#       {"chat_id": "oc_abc123", "name": "管理层群", "score": 1.0}
#     ]
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
#   "ok": true,
#   "result": [
#     {"open_id": "ou_xyz123", "display_name": "张三"}
#   ]
# }
```

### Step 3: Propose Meeting Slots

```bash
# Start a multi-round negotiation for the candidate time slots
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  start-negotiation \
    --title "项目汇报会" \
    --initiator-open-id "ou_owner" \
    --duration-minutes 30 \
    --attendee-open-id "ou_xyz123" \
    --attendee-open-id "ou_abc456" \
    --candidate-slot "2026-04-28 15:00" \
    --candidate-slot "2026-04-28 15:30"

# Expected output (JSON):
# {
#   "ok": true,
#   "result": {
#     "negotiation_id": "prop_123abc",
#     "status": "negotiating",
#     "current_round": 1
#   }
# }
```

### Step 4: Create Meeting After Agreement

```bash
# Create the final calendar event directly when the attendee list is already known
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  create-meeting \
    --title "项目汇报会" \
    --description "按照既定时间进行项目进度汇报" \
    --start-time "2026-04-28 15:00" \
    --end-time "2026-04-28 15:30" \
    --attendee "ou_xyz123" \
    --attendee "ou_abc456" \
    --initiator-open-id "ou_owner"

# Expected output (JSON):
# {
#   "ok": true,
#   "result": {
#     "event_id": "event_123xyz",
#     "join_url": "https://feishu.example.com/calendar/event/event_123xyz"
#   }
# }
```

### Step 5: Finalize Negotiation After Agreement

```bash
# Finalize a negotiation state and fan out the meeting to participant calendars
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  finalize-negotiation \
    --state-json '<state-json>' \
    --description "会议已创建，请准时参加"

# Expected output (JSON):
# {
#   "ok": true,
#   "result": {
#     "meeting_owner_open_id": "ou_owner",
#     "meetings": []
#   }
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

## Card 2.0 Interaction Mode: Alternatives and Migration

### Compatibility Baseline

- In **custom bot webhook mode**, Card 2.0 is treated as one-way push UI for this skill.
- Do not emit callback-style submit interactions in custom bot mode.
- Use one of these alternatives instead:
  - **Option A (preferred in webhook mode)**: markdown guidance and chat text reply collection.
  - **Option B**: URL-only button flow (`open_url`) that redirects to an external form page.

### Hard Guardrails for Custom Bot Mode

- Never emit unsupported action container tags for submit flows.
- If required fields are missing, always render `schema_form` as display guidance plus text instructions to reply in chat.
- Treat user replies as the source of truth for form submission in webhook mode.

### Migration Checklist: Custom Bot -> App Bot Callback Flow

Use this checklist when you need true in-card submit behavior.

1. Platform setup:
  - Create or reuse a Feishu **App Bot** (not custom bot).
  - Enable bot capabilities for receiving and replying to messages.
  - Enable card callback handling in app configuration.
2. Permissions and events:
  - Apply required message and bot interaction permissions.
  - Subscribe to message/card callback events needed for submit processing.
3. Backend endpoint:
  - Add a dedicated callback endpoint for card interactions.
  - Verify request signatures and reject invalid callbacks.
  - Enforce idempotency on callback processing using callback/event IDs.
4. Data contract:
  - Map card field payloads to the meeting contract (`title`, `time`, `duration`, `attendees`).
  - Reuse existing server-side validation before any scheduling side effects.
5. Runtime branching:
  - Keep a mode switch in backend routing:
    - `custom_bot`: non-callback flow (markdown/open_url/text reply).
    - `app_bot`: callback submit flow.
  - Do not mix callback payload assumptions into custom bot pipeline.
6. Card rendering:
  - For `app_bot`, use callback-capable Card 2.0 interaction components.
  - For `custom_bot`, continue rendering non-callback-safe content only.
7. Rollout and fallback:
  - Ship behind a feature flag for selected workspaces.
  - Keep text-reply fallback active if callback validation fails.
8. Regression coverage:
  - Add tests proving custom bot path never emits callback-only elements.
  - Add tests proving app bot callback payloads are parsed and validated.
  - Add tests for callback signature failure and idempotency replay.

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
- Never prefill or preselect a required field merely to keep the flow moving. If `duration_value`, `duration_unit`, attendees, or another required field is uncertain, leave it for the user to clarify in the form.
- `meeting_description` is optional and must remain `required: false`.
- If the user already supplied some fields, keep the same schema keys and only ask for the missing ones.
- If the attendee names might be ambiguous, still collect them in `attendees` first; resolve them through backend contact search after submit.

## Pre-Create Review and Approval A2UI Contract

After attendee resolution and before `create-meeting`/`finalize-negotiation`, if any value is inferred or defaulted, emit a review form with prefilled defaults and an explicit approve/edit choice.

Use this `a2ui` block shape:

```a2ui
{
  "version": "1.0",
  "root": {
    "component": "schema_form",
    "props": {
      "title": "确认并审批会议创建",
      "submitLabel": "提交确认",
      "followUp": "请根据审批结果继续：approve 则创建会议，edit 则先修改参数。",
      "fields": [
        {
          "key": "meeting_title",
          "label": "会议主题",
          "type": "text",
          "required": true,
          "default": "<resolved_or_default_title>"
        },
        {
          "key": "meeting_time",
          "label": "会议时间",
          "type": "text",
          "required": true,
          "default": "<resolved_or_default_time>"
        },
        {
          "key": "duration_value",
          "label": "会议时长数值",
          "type": "number",
          "required": true,
          "default": 30
        },
        {
          "key": "duration_unit",
          "label": "会议时长单位",
          "type": "select",
          "required": true,
          "options": [
            { "label": "分钟", "value": "分钟" },
            { "label": "小时", "value": "小时" }
          ],
          "default": "分钟"
        },
        {
          "key": "timezone",
          "label": "时区",
          "type": "text",
          "required": true,
          "default": "Asia/Shanghai"
        },
        {
          "key": "organizer_identity",
          "label": "组织者",
          "type": "text",
          "required": true,
          "default": "<resolved_organizer>"
        },
        {
          "key": "initiator_identity",
          "label": "发起人",
          "type": "text",
          "required": true,
          "default": "<resolved_initiator>"
        },
        {
          "key": "organizer_approval",
          "label": "组织者审批",
          "type": "select",
          "required": true,
          "options": [
            { "label": "approve", "value": "approve" },
            { "label": "edit", "value": "edit" }
          ]
        },
        {
          "key": "approval_note",
          "label": "审批备注",
          "type": "textarea",
          "required": false,
          "placeholder": "可选：记录组织者审批说明"
        }
      ]
    }
  }
}
```

Rules for review/approval form:

- This review form is required before create-event when inferred/defaulted values exist.
- If organizer and initiator differ, `organizer_approval=approve` is mandatory before calling any create-event command.
- If user chooses `edit`, revise fields and re-confirm; do not create event in the same step.
- Keep audit clarity in final response: include organizer, initiator, and whether organizer approval was obtained.

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