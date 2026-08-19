# Gemini Adapter — Limitations

Capability and compatibility notes for the two Gemini-family runtimes
(Gemini CLI and Gemini API) and how Otaman skills map onto each. The Gemini
adapters in `gemini.py` are drafts; this document records what maps cleanly and
where the runtime constraints are.

---

## Overview

There are two distinct Gemini-family runtimes that require separate adapters:

1. **Gemini CLI** (`gemini-cli`) — Google's open-source CLI tool (equivalent to
   Claude Code).  Adopted the SKILL.md standard in Dec 2025 as part of the
   cross-LLM skill standard (Anthropic + OpenAI + Cursor + Gemini CLI + Windsurf
   + Grok Build).  Reads SKILL.md natively.

2. **Gemini API** (`gemini-api`) — Programmatic access via `google-generativeai`
   SDK or Vertex AI.  No native SKILL.md reader.  Skills are injected via the
   `system_instruction` parameter.

---

## Capability mapping

### Gemini CLI

Registration mechanism: **file-based** (identical to Claude Code).
Adapter: `GeminiCliAdapter` (wraps the same file-placement logic as `ClaudeCodeAdapter`).

| Skill capability | Maps to Gemini CLI? | Compatibility | Notes |
|---|---|---|---|
| SKILL.md frontmatter (name, description, triggers) | ✅ Yes | `full` | Native reader |
| Skill body (markdown instructions) | ✅ Yes | `full` | Loaded on-demand |
| `references/` sibling assets | ✅ Yes | `full` | Copied alongside SKILL.md |
| System prompt injection | ✅ Yes | `full` | Via descriptions in plugin |
| Trigger-cue matching | ✅ Yes | `full` | Same mechanism as Claude Code |
| MCP server binding | ⚠️ Partial | `partial` | Gemini CLI supports MCP but subset varies by version; some tools not available |
| File system tools (read/write/edit) | ⚠️ Partial | `partial` | Available but scope rules differ from Claude Code; sandboxing may differ |
| Computer-use (screenshot, mouse, keyboard) | ❌ No | `unsupported` | Not available in Gemini CLI as of 2026-05 |
| Multi-turn memory | ✅ Yes | `full` | Session state maintained |
| Image/audio input | ✅ Yes | `full` | Gemini natively multimodal |
| Web fetch/search | ✅ Yes | `full` | Via Gemini's built-in grounding |

**Default compatibility for skills not declaring `provider_support:`**: `full`.
Most Otaman skills (text-in / text-out advisory skills) work cleanly.  Only skills
that depend on `computer-use` or assume exact Claude Code tool API shapes need
explicit `provider_support.gemini-cli` declarations.

---

### Gemini API

Registration mechanism: **instruction injection** (identical to OpenAI Agents SDK).
Adapter: `GeminiApiAdapter` (wraps the same instructions-block logic as `OpenAIAgentsAdapter`).

| Skill capability | Maps to Gemini API? | Compatibility | Notes |
|---|---|---|---|
| SKILL.md description (injected into system_instruction) | ✅ Yes | `full` | Injected as system instruction text |
| Trigger cues in system instruction | ✅ Yes | `full` | Model matches triggers from instructions |
| Skill body (on-demand loading) | ❌ No | `unsupported` | No mechanism to load bodies on-demand; full body must be in system instruction or user turn |
| Multi-turn memory | ⚠️ Partial | `partial` | Stateless per request; history must be passed explicitly in each API call |
| Function calling | ✅ Yes | `full` | Gemini natively supports function declarations |
| MCP server binding | ❌ No | `unsupported` | Not available via API (only CLI tool-based) |
| File system tools | ❌ No | `unsupported` | Not available via Gemini API |
| Computer-use | ❌ No | `unsupported` | Not available |
| Image/audio input | ✅ Yes | `full` | Gemini natively multimodal |
| Web grounding | ⚠️ Partial | `partial` | Google Search grounding available but requires specific API config; not all skill invocation patterns are compatible |

**Default compatibility for skills not declaring `provider_support:`**: `full`.
However, skills that rely on on-demand body loading (bodies loaded on
activation, not at session start) will behave differently — the body must
either be included in the system instruction at startup or passed in the user turn.

---

## Skill body loading compatibility gap — Gemini API

Otaman's skill-loading model is:
> Descriptions in system prompt at session start; bodies on-demand

Claude Code and Gemini CLI both support this natively (the runtime controls when
the full skill body is loaded into context).  The Gemini API does not — there is
no equivalent of "load skill body when triggered."  For Gemini API:

- **Option A**: Include full body in system instruction at startup (higher token cost,
  works immediately).
- **Option B**: Pass skill body in user turn at the point of invocation (lower startup
  cost, requires runner-side logic to detect activation and inject body).

Recommendation: the `GeminiApiAdapter` generates instructions block with descriptions
only (consistent with the descriptions-at-startup / bodies-on-demand model).  The
runner that consumes `SKILL_INSTRUCTIONS` is
responsible for on-demand body injection if needed.  Add a `body_for(skill_name) -> str`
helper to `skills_block.py` in a follow-on implementation change.

---

## `provider_support:` recommendations for existing Otaman skills

The existing Otaman catalog (advisory skills: `cto-advisor`, `knowledge-capture`,
`project-estimator`) maps cleanly to `full` for both Gemini runtimes — no explicit
declarations needed.

For skills that would declare limitations:

```yaml
# Example: a skill that uses computer-use (not available on Gemini)
provider_support:
  gemini-cli: unsupported
  gemini-api: unsupported
  claude-code: full
  openai-agents: unsupported
provider_notes:
  gemini-cli: "computer-use tools not available in Gemini CLI"
  gemini-api: "computer-use tools not available in Gemini API"
```

```yaml
# Example: a skill that relies on MCP servers (partial on Gemini CLI, unsupported on API)
provider_support:
  gemini-cli: partial
  gemini-api: unsupported
  claude-code: full
  openai-agents: full
provider_notes:
  gemini-cli: "MCP tool subset varies; verify specific tools are available"
  gemini-api: "MCP not available via API; use CLI runtime"
```

---

## Implementation completeness

`GeminiCliAdapter` and `GeminiApiAdapter` in `gemini.py` are **sketches**:
- Core logic: complete (same file-placement / instruction-injection patterns as
  Claude Code and OpenAI adapters respectively)
- Tests: NOT written (task says "sketch" + research note; not "spike with full tests")
- Live activation: NOT verified (requires Gemini CLI / Gemini API key)

A production implementation would:
1. Write tests mirroring `test_claude_code_adapter.py` and `test_openai_agents_adapter.py`
2. Run live activation against a Gemini CLI session and a Gemini API call
3. Handle Gemini CLI's specific plugin directory path convention (TBD — check Gemini CLI docs)
4. Add `body_for(skill_name)` to `GeminiApiAdapter.build_instructions()` output for
   on-demand body loading

---

## Refactoring opportunity

All four adapters (Claude Code, OpenAI Agents, Gemini CLI, Gemini API) fall into
two families:

| Family | Mechanism | Adapters |
|---|---|---|
| SKILL.md-native (file-based) | Place `SKILL.md` at `<target>/skills/<name>/SKILL.md` | `ClaudeCodeAdapter`, `GeminiCliAdapter` |
| Instruction-injection | Write `skills_block.md` + `skills_block.py` | `OpenAIAgentsAdapter`, `GeminiApiAdapter` |

A follow-on refactor could extract:
- `SkillMdFileAdapter(runtime_id)` — base class for file-based adapters
- `InstructionInjectionAdapter(runtime_id)` — base class for instruction adapters

This is deferred to a future adapter-implementation change.
