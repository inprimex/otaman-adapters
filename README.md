# otaman-adapters

> **Otaman platform:** [otaman-core](https://github.com/inprimex/otaman-core) · [otaman-cli](https://github.com/inprimex/otaman-cli) · [otaman-plugin](https://github.com/inprimex/otaman-plugin) · [otaman-bridge](https://github.com/inprimex/otaman-bridge) · [otaman-runner](https://github.com/inprimex/otaman-runner) · **otaman-adapters (you are here)**

Harness drivers for Otaman — one subpackage per supported AI coding runtime,
translating between the Otaman Adapter Protocol and each harness's native skill
registration and event format. A separate Easy8 (Redmine-core) adapter provides
PM issue sync.

## Status

The Claude Code adapter and OpenAI Agents SDK adapter are implemented, along
with the Easy8 PM-sync adapter and the compliance capability model. The Gemini
adapters (CLI and API) are drafts. The harness-to-session transcript pipeline
and approval-intercept wiring do not exist yet — those depend on otaman-core
interfaces that are still in design.

| Component | State |
|---|---|
| `ClaudeCodeAdapter` (skill registration) | **Implemented** |
| `OpenAIAgentsAdapter` (skill instruction injection) | **Implemented** |
| `Easy8Adapter` (Redmine-core PM issue sync) | **Implemented** |
| `AdapterCapabilities` / `DataClassification` | **Implemented** |
| `GeminiCliAdapter` (skill registration) | Draft (not production-ready) |
| `GeminiApiAdapter` (skill instruction injection) | Draft (not production-ready) |
| Transcript translation (native format → `SessionEvent`) | Not started |
| Approval-intercept wiring | Not started |
| Cancellation propagation | Not started |
| `codex-cli` adapter | Not started |

## What this repo owns

- `SkillAdapter` Protocol — the contract every runtime adapter satisfies
- `AdapterCapabilities` / `DataClassification` — per-adapter compliance
  declarations consumed by otaman-router
- **Claude Code adapter**: places each active skill's `SKILL.md` at
  `<target>/skills/<name>/SKILL.md`; injects `[CAVEAT: …]` annotations for
  partially-compatible skills; handles `full`, `partial`, and `unsupported`
  compatibility levels
- **OpenAI Agents SDK adapter**: skill registration via instruction injection;
  writes `skills_block.md` + `skills_block.py` (`SKILL_INSTRUCTIONS`) to the
  target directory for use at `Agent` construction time
- **Easy8 (Redmine-core) PM-sync adapter**: create/update issues, add comments,
  register webhooks, look up users, and `resolve_pm_user_id` against a
  `human-roster`; REST client plus an optional `Easy8McpClient`
- **Gemini CLI adapter** (draft): file-based layout identical to Claude Code;
  Gemini CLI reads SKILL.md natively
- **Gemini API adapter** (draft): instruction injection identical to OpenAI
  Agents; no native SKILL.md reader in the `google-generativeai` SDK
- Transcript translation (native harness format → normalised `SessionEvent`
  stream) — _planned_
- Approval-intercept wiring (hooks into the harness approval flow) — _planned_
- Cancellation propagation — _planned_

## What this repo does NOT own

- The Adapter Protocol definition is shared with otaman-core; a local copy of
  `SkillAdapter` lives here pending the core publish
- Routing decisions (otaman-router consults the capabilities declared here)
- Session lifecycle management (otaman-bridge)

## Compliance posture per LLM adapter

Each LLM-runtime adapter declares which data-classification tiers its *default*
backend is certified for. See [docs/adapter-compliance.md](docs/adapter-compliance.md)
for the full rationale. (The Easy8 PM-sync adapter is not an LLM data-routing
adapter and is not covered by this table.)

| Adapter | Default clearance | PHI/REGULATED path |
|---|---|---|
| `claude-code` | INTERNAL, SENSITIVE | Bedrock-Anthropic + AWS BAA (operator-configured) |
| `openai-agents` | INTERNAL, SENSITIVE | Azure OpenAI + Microsoft BAA (operator-configured) |
| `gemini-cli` | INTERNAL, SENSITIVE | Google Cloud Healthcare-certified Vertex AI (operator-configured) |
| `gemini-api` | INTERNAL, SENSITIVE | Google Cloud Healthcare-certified Vertex AI (operator-configured) |

## Quick start

Requires **Python 3.10+** and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev               # install with dev/test extras
uv run pytest                     # run the test suite
uv run ruff check .               # lint  (ce-lint-standard baseline)
uv run ruff format --check .      # format check
```

```python
from pathlib import Path

from otaman_adapters import ClaudeCodeAdapter, load_skill

# Load skills from SKILL.md files, then register them for Claude Code.
skills = [load_skill(Path("skills/my-skill/SKILL.md"))]
results = ClaudeCodeAdapter().register(skills, target_dir=Path(".otaman/plugin"))
```

## Dependencies

- Python >= 3.10
- `pyyaml >= 6.0`
- `otaman-core` (optional at runtime; `AdapterCapabilities` /
  `DataClassification` are duplicated locally until otaman-core publishes them)

## License

This repository is the Otaman **Community Edition** and is licensed under
**AGPL-3.0-only** — see [LICENSE](LICENSE). Commercial and dual licenses are
available from Inprimex Lab LLC: licensing@inprimex.com. Contributions are
accepted under the Contributor License Agreement — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## See also

- [docs/](docs/) — adapter behavior and compliance reference
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution workflow and CLA
- [SECURITY.md](SECURITY.md) — reporting security vulnerabilities
