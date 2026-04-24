---
name: feishu-bot-meeting-coordinator
description: >
  Coordinate Feishu bot-assisted contact search and meeting scheduling for
  workspace users. Use this skill when the Semantier backend is configured to
  search the bot's visible contacts and create calendar meetings on the bot's
  calendar without relying on lark-cli.
version: 1.0.0
author: Semantier
license: MIT
tags:
  - feishu
  - lark
  - calendar
  - meetings
  - contacts
triggers:
  - schedule a feishu meeting
  - find feishu contacts
  - invite contacts in feishu
metadata:
  hermes:
    tags: [feishu, lark, calendar, meetings, contacts]
    config:
      - key: feishu.bot.identity
        description: Human-readable organizer identity for the installed Feishu bot
        default: ""
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

This skill is for the direct Feishu bot/API path. Do not switch to `lark-cli` unless the user explicitly asks for a CLI workflow.

## Runtime Expectations

This skill assumes the Semantier backend owns the Feishu integration surface, including:

- Feishu app credentials stored as backend secrets, not in skill config
- contact search exposed by the backend
- meeting creation exposed by the backend
- deterministic config persistence under `skills.config.feishu.bot.*`

If those runtime capabilities are unavailable, state that the backend integration is missing instead of inventing manual steps.

## Installed Skill Config

When this skill is installed into a workspace, use the configured values as follows:

- `feishu.bot.identity`: treat as the organizer identity to reference in summaries and confirmations
- `feishu.bot.timezone`: use as the default timezone for proposed meeting times
- `feishu.bot.contact_scope`: assume this describes which contacts are expected to be discoverable by the bot

## Operating Rules

1. Ask for the meeting goal, date or time window, duration, and attendee names if they are missing.
2. Resolve attendees through the backend Feishu contact search rather than guessing account identifiers.
3. Confirm ambiguous contact matches before creating the meeting.
4. Create meetings on the bot's calendar, with the bot acting as organizer.
5. Summarize invitees, timezone, and schedule before final confirmation when the user request is ambiguous.
6. Treat app secrets, user tokens, and webhook secrets as backend-owned secrets. Never ask the user to paste them into chat or store them in skill config.

## Missing Input A2UI Contract

When the user wants to schedule a meeting but required fields are missing, do not ask with a free-form bullet list like `根据技能说明，我需要...`.

Instead, emit exactly one fenced `a2ui` JSON block using `schema_form`, then add one short plain-language sentence below it.

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

- If no matching contacts are found, report that clearly and ask for a refined name, department, or alias.
- If multiple contacts match, present the candidates and ask the user to choose.
- If the calendar operation fails, preserve the resolved attendee candidates so the user does not need to repeat them.