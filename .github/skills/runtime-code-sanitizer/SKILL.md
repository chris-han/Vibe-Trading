---
name: runtime-code-sanitizer
description: "Add sanitizer functions and prompt guards for components that generate code at runtime (ECharts JSON, Mermaid diagrams, SQL, Python scripts). Use when: adding a new LLM output type that gets executed or rendered; reviewing whether an existing generator has validation; auditing runtime-generated code paths; fixing render crashes caused by invalid LLM output. Also installs the pre-commit hook that runs the checker automatically on every commit."
---

# Runtime Code Sanitizer

## Purpose

Any component that takes LLM-generated text and passes it to a renderer or executor (ECharts, Mermaid, Python `exec`, SQL, bash) must have:

1. **A server-side sanitizer** — post-processes LLM output before it is stored or streamed to the frontend
2. **A prompt guard** — adds explicit rules to the system prompt so the LLM generates valid output in the first place
3. **A pre-commit checker** — `scripts/check_sanitizers.py` verifies both exist whenever relevant files change

---

## When to Use This Skill

- You are adding a new `````echarts`````, `````mermaid`````, `````sql`````, or other rendered/executed code fence type
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
"- ECharts dual-axis rule: when any series uses \"yAxisIndex\": N you MUST define \"yAxis\" "
"  as a JSON array with N+1 elements. The key \"yAxis2\" does not exist in ECharts.\n"
```

Rules must be:
- Positive ("you MUST ...") not just negative
- Specific about the exact API shape
- Fallback-aware ("fall back to a Markdown table if unsure")

### 3. Add / update the sanitizer function

Add a `_sanitize_<type>_blocks(text: str) -> str` function near `_OUTPUT_FORMAT_PROMPT` in `service.py`. The function must:
- Use a compiled regex to extract fenced blocks (e.g. ` ```echarts ... ``` `)
- Parse the block content
- Apply each repair deterministically
- Return the original text unchanged if parsing fails
- Only rewrite a block when a repair was actually needed (`changed` flag pattern)

See the existing `_sanitize_echarts_blocks()` in [service.py](../../../../agent/src/session/service.py) as the canonical example.

### 4. Wire the sanitizer into the output pipeline

In `_run_with_agent()`, call the sanitizer on `final_text` before writing `report.md`:

```python
final_text = _sanitize_echarts_blocks(final_text)
# add new sanitizer calls here:
# final_text = _sanitize_mermaid_blocks(final_text)
```

### 5. Register the type in the checker

Add the new type to [scripts/check_sanitizers.py](./scripts/check_sanitizers.py) so the pre-commit hook validates it.

### 6. Install the pre-commit hook (once per clone)

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

Every sanitizer function must satisfy:

| Requirement | Why |
|---|---|
| Idempotent | Calling twice must not change output |
| Fail-open | Parse error → return original text, never raise |
| Only change what's broken | Don't reformat valid output |
| Log repairs | `logger.debug("sanitized %s blocks", count)` |

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

| Type | Sanitizer | Prompt guard | Pre-commit check |
|---|---|---|---|
| ECharts JSON | `_sanitize_echarts_blocks()` | `_OUTPUT_FORMAT_PROMPT` dual-axis rule | ✅ |

---

## Adding a New Type — Checklist

- [ ] Prompt guard added to `_OUTPUT_FORMAT_PROMPT`
- [ ] `_sanitize_<type>_blocks()` function added before the imports block
- [ ] Sanitizer called on `final_text` in `_run_with_agent()`
- [ ] Type registered in `scripts/check_sanitizers.py` `REQUIRED_TYPES`
- [ ] Pre-commit hook installed (`--install-hook`)
- [ ] Table row added in "Known Sanitized Types" above
