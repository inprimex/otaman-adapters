# otaman-adapters

> **Otaman platform:** [otaman-core](https://github.com/inprimex/otaman-core) · [otaman-cli](https://github.com/inprimex/otaman-cli) · [otaman-plugin](https://github.com/inprimex/otaman-plugin) · [otaman-bridge](https://github.com/inprimex/otaman-bridge) · [otaman-runner](https://github.com/inprimex/otaman-runner) · **otaman-adapters (you are here)**

Harness drivers for Otaman — one subpackage per supported AI coding runtime,
translating between the Adapter Protocol and each harness's native skill
registration and event format.

## Status

More code exists here than the scaffold label suggests. The Claude Code adapter
and OpenAI Agents SDK adapter are implemented. The Gemini adapters (CLI and
API) are written as drafts. The harness-to-session transcript pipeline and
approval intercept wiring do not exist yet — those depend on otaman-core
interfaces that are still in design.

| Adapter | State | Step |
|---|---|---|
| `ClaudeCodeAdapter` (skill registration) | **Implemented** | 1 |
| `OpenAIAgentsAdapter` (skill instruction injection) | **Implemented** | 1 |
| `GeminiCliAdapter` (skill registration) | Draft (not production-ready) | 2 |
| `GeminiApiAdapter` (skill instruction injection) | Draft (not production-ready) | 2 |
| `AdapterCapabilities` / `DataClassification` | **Implemented** | 1 |
| Transcript translation (native format -> SessionEvent) | Not started | 4 |
| Approval intercept wiring | Not started | 4 |
| Cancellation propagation | Not started | 4 |
| `codex-cli` adapter (v2) | Not started | 6 |

## What this repo owns

-  Protocol — the contract every runtime adapter must satisfy
-  /  — per-adapter compliance
  declarations consumed by otaman-router
- **Claude Code adapter**: places each active skill's  at
  ; injects  annotations
  for partially-compatible skills; handles , , 
  compatibility levels
- **OpenAI Agents SDK adapter**: skill registration via instruction injection;
  writes  +  () to the
  target directory for use at  construction time
- **Gemini CLI adapter** (draft): file-based layout identical to Claude Code;
   reads SKILL.md natively
- **Gemini API adapter** (draft): instruction injection identical to OpenAI
  Agents; no native SKILL.md reader in the  SDK
- Transcript translation (native harness format -> normalised 
  stream) _(Step 4)_
- Approval intercept wiring (hooks into harness approval flow) _(Step 4)_
- Cancellation propagation _(Step 4)_

## What this repo does NOT own

- The Adapter Protocol itself (owned by otaman-core; local copy of
   exists here pending the core publish)
- Routing decisions (otaman-router consults capabilities declared here)
- Session lifecycle management (otaman-bridge)

## Compliance posture per adapter

| Adapter | Default clearance | PHI/REGULATED path |
|---|---|---|
| `claude-code` | INTERNAL, SENSITIVE | Bedrock-Anthropic + AWS BAA (EE, operator-configured) |
| `openai-agents` | INTERNAL, SENSITIVE | Azure OpenAI + Microsoft BAA (operator-configured) |
| `gemini-cli` | INTERNAL, SENSITIVE | Google Cloud Healthcare-certified Vertex AI (operator-configured) |
| `gemini-api` | INTERNAL, SENSITIVE | Google Cloud Healthcare-certified Vertex AI (operator-configured) |

## License

The Claude Code adapter is AGPL-3.0 (same as Claude Code plugin). Other
adapters use the project's default license.

## Quick start

```bash
uv pip install -e ".[dev]"
pytest
```

```python
from pathlib import Path
from otaman_adapters import ClaudeCodeAdapter, OpenAIAgentsAdapter
from otaman_adapters.models import Skill

# Example: register skills for Claude Code
adapter = ClaudeCodeAdapter()
results = adapter.register(skills, target_dir=Path(".otaman/plugin"))
```

## Dependencies

- Python >= 3.10
- `pyyaml >= 6.0`
- `otaman-core` (pending publish; `AdapterCapabilities` temporarily duplicated here)

## See also

- [phased-roadmap.md](https://github.com/inprimex/otaman-meta/blob/main/phased-roadmap.md) — Step 1/4/6 context
- [polyrepo-structure.md](https://github.com/inprimex/otaman-meta/blob/main/polyrepo-structure.md) — repo ownership map
- [ADRs](https://github.com/inprimex/otaman-meta/blob/main/adrs/) — architecture decisions
- [otaman-meta](https://github.com/inprimex/otaman-meta) — architecture canon
