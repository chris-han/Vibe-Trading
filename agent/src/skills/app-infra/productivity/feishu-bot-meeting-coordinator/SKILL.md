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