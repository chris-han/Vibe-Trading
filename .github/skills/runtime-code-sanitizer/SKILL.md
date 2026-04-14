---
name: runtime-code-sanitizer
description: "Add prompt guards for components that generate code at runtime (VChart JSON, Mermaid diagrams, SQL, Python scripts). Use when: adding a new LLM output type that gets executed or rendered; reviewing whether an existing generator has validation; auditing runtime-generated code paths; fixing render crashes caused by invalid LLM output. Also installs the pre-commit hook that runs the checker automatically on every commit."
---

# Runtime Code Sanitizer

## Purpose

Any component that takes LLM-generated text and passes it to a renderer or executor (VChart, Mermaid, Python `exec`, SQL, bash) must have:

1. **A prompt guard** — adds explicit rules to the system prompt so the LLM generates valid output in the first place
2. **A pre-commit checker** — `scripts/check_sanitizers.py` verifies the prompt guard whenever relevant files change

---

## When to Use This Skill

- You are adding a new `````vchart`````, `````mermaid`````, `````sql`````, or other rendered/executed code fence type
- A renderer is crashing with undefineds, parse errors, or syntax errors from LLM output
- You are onboarding a new LLM output channel (Feishu card, Slack block, etc.)
- You want to audit what runtime-generated code paths currently have sanitization

---

## Procedure

### 1. Identify the generator

Find the Python file that builds the system/ephemeral prompt and calls the agent. In this project: `agent/src/session/service.py` — look for `_OUTPUT_FORMAT_PROMPT` and `ephemeral_system_prompt=`.

### 2. Add / update the prompt guard

In `_OUTPUT_FORMAT_PROMPT`, add an explicit rule for the output type. Example pattern:

```
"- Prefer VChart JSON blocks for new charts.\n"
"- Render tables as Markdown pipe-tables.\n"
"- Use Mermaid for diagrams and flowcharts.\n"
```

Rules must be:
- Positive ("you MUST ...") not just negative
- Specific about the exact API shape
- Fallback-aware ("fall back to a Markdown table if unsure")

### 3. Register the guard in the checker

Add the new rule to [scripts/check_sanitizers.py](./scripts/check_sanitizers.py) so the pre-commit hook validates it.

### 4. Install the pre-commit hook (once per clone)

```bash
cp .github/skills/runtime-code-sanitizer/scripts/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Or run:
```bash
python .github/skills/runtime-code-sanitizer/scripts/check_sanitizers.py --install-hook
```

---

## Sanitizer Contract

Every prompt guard must satisfy:

| Requirement | Why |
|---|---|
| States the positive form | "MUST use X" not just "never use Y" |
| Names the exact key/format | Avoids ambiguity for the LLM |
| Provides a fallback | LLM knows what to do when unsure |
| One rule per output type | Keeps the prompt scannable |

---

## Prompt Guard Contract

Every prompt guard rule must satisfy:

| Requirement | Why |
|---|---|
| States the positive form | "MUST use X" not just "never use Y" |
| Names the exact key/format | Avoids ambiguity for the LLM |
| Provides a fallback | LLM knows what to do when unsure |
| One rule per output type | Keeps the prompt scannable |

---

## Known Sanitized Types

| Type | Prompt guard | Pre-commit check |
|---|---|---|---|
| VChart JSON | `_OUTPUT_FORMAT_PROMPT` VChart preference rule | ✅ |
| Mermaid diagrams | `_OUTPUT_FORMAT_PROMPT` Mermaid rule | ✅ |
| Markdown tables | `_OUTPUT_FORMAT_PROMPT` Markdown table rule | ✅ |

---

## Adding a New Type — Checklist

- [ ] Prompt guard added to `_OUTPUT_FORMAT_PROMPT`
- [ ] Rule registered in `scripts/check_sanitizers.py`
- [ ] Pre-commit hook installed (`--install-hook`)
- [ ] Table row added in "Known Sanitized Types" above
