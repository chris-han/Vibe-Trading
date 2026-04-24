---
name: feishu-bot-meeting-coordinator
description: >
  Coordinate Feishu bot-assisted contact search and meeting scheduling for
  workspace users. Use this skill when the Semantier backend is configured to
  search the bot's visible contacts and create calendar meetings on the bot's
  calendar.
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
- create calendar meetings on the bot's calendar
- invite user-selected contacts to the meeting

This skill is for the direct Feishu bot/API path.

## Runtime Expectations

This skill assumes Feishu app credentials are backend-owned secrets, while the deterministic execution surface lives inside this skill directory.

Before attempting contact search or meeting creation, load the helper code with `skill_view(name="feishu-bot-meeting-coordinator", file_path="scripts/feishu_bot_api.py")` and use that helper instead of inventing raw HTTP calls, lark-cli commands, or ad hoc terminal scripts.

This skill ships a deterministic helper at `scripts/feishu_bot_api.py` for:

- tenant token acquisition using backend-owned env vars
- contact search from the bot-visible directory
- meeting creation on the bot calendar
- deterministic config persistence under `skills.config.feishu.bot.*`

If those runtime capabilities are unavailable, state that the required Feishu env/config is missing instead of inventing manual steps.

## Execution Surface

- Load `scripts/feishu_bot_api.py` with `skill_view(...)` before using it.
- Use the helper's deterministic Python API or CLI surface for contact search and meeting creation.
- Prefer the helper over direct handwritten `requests` code so the contact ranking and attendee resolution rules stay consistent.
- Do not use `lark-cli` unless the user explicitly asks for it.

## Installed Skill Config

When this skill is installed into a workspace, use the configured values as follows:

- `feishu.bot.identity`: treat as the organizer identity to reference in summaries and confirmations; use `semantier` as the default organizer identity for Feishu functions
- `feishu.bot.timezone`: use as the default timezone for proposed meeting times
- `feishu.bot.contact_scope`: assume this describes which contacts are expected to be discoverable by the bot

## Operating Rules

1. Use the Feishu bot identity `semantier` as the organizer identity for contact search, meeting creation, and meeting summaries unless an explicit workspace config override is provided.
2. **MANDATORY**: When any required meeting field is missing, you MUST emit the `a2ui` `schema_form` block defined in the **Missing Input A2UI Contract** section below. A free-form markdown bullet list asking for the same fields is NEVER acceptable — even when reading the skill for the first time.
3. Resolve attendees through `scripts/feishu_bot_api.py` rather than guessing account identifiers.
4. Confirm ambiguous contact matches before creating the meeting.
5. Create meetings on the bot's calendar, with the bot acting as organizer.
6. Summarize invitees, timezone, and schedule before final confirmation when the user request is ambiguous.
7. Treat app secrets, user tokens, and webhook secrets as backend-owned secrets. Never ask the user to paste them into chat or store them in skill config.

## Helper Entry Points

- Contact search CLI: `python scripts/feishu_bot_api.py search-contacts --query "Amy Q" --limit 5`
- Meeting creation CLI: `python scripts/feishu_bot_api.py create-meeting --title "项目同步" --start-time "2026-04-24 15:40" --end-time "2026-04-24 16:10" --attendee "Chris Han" --attendee "Amy Q"`
- Python API: import `search_contacts(...)` and `create_meeting(...)` from `scripts/feishu_bot_api.py` when the runtime prefers in-process execution.

The helper expects `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, and optionally `FEISHU_DOMAIN` in the environment.

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
- meeting title
- start and end time with timezone
- invited contacts
- any contacts that could not be resolved

## Failure Handling

 If no matching contacts are found, report that clearly and ask for a refined name, department, or alias.
 If multiple contacts match, present the candidates and ask the user to choose.
 If the calendar operation fails, preserve the resolved attendee candidates so the user does not need to repeat them.