# otaman-adapters — working in this repository

`otaman-adapters` provides the harness drivers for the Otaman platform: one
subpackage per supported AI coding runtime, each translating between the Otaman
Adapter Protocol and that harness's native skill-registration and event format.
The Claude Code and OpenAI Agents SDK adapters are implemented; the Gemini CLI
and API adapters are drafts. An Easy8 (Redmine-core) adapter provides PM issue
sync.

## Development

Requires **Python 3.10+** and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev               # install with dev/test extras
uv run pytest                     # run the test suite
uv run ruff check .               # lint  (ce-lint-standard baseline)
uv run ruff format --check .      # format check
```

## Repository layout

| Path | Contents |
|---|---|
| `src/otaman_adapters/adapter.py` | The Adapter Protocol and shared registration interface |
| `src/otaman_adapters/loader.py` | SKILL.md discovery and frontmatter parsing |
| `src/otaman_adapters/claude_code.py` | Claude Code adapter — SKILL.md file registration |
| `src/otaman_adapters/openai_agents.py` | OpenAI Agents SDK adapter — system-instruction injection |
| `src/otaman_adapters/gemini.py` | Gemini CLI / API adapters (draft) |
| `src/otaman_adapters/easy8.py` | Easy8 (Redmine-core) PM issue-sync adapter |
| `src/otaman_adapters/capabilities.py` | Data-classification / compliance capability model |
| `src/otaman_adapters/models.py` | Shared skill / result dataclasses and compatibility levels |
| `src/otaman_adapters/_paths.py` | Path-safety helpers (skill-name traversal guard) |
| `tests/` | pytest suite covering every adapter and the path-traversal guard |

## Conventions

- Branch per change; all changes land via pull request against `main`.
- Conventional-commit style messages; sign off commits (`git commit -s`) per
  `CONTRIBUTING.md`.
- Include tests for behavioural changes; keep `ruff check .` and
  `ruff format --check .` clean before opening a PR.
- The skill-name guard in `_paths.py` is a security boundary (prevents path
  traversal during skill registration) — never bypass it, and keep its tests in
  `tests/test_path_traversal_guard.py` green.

## For AI assistants / automated contributors

Follow `CONTRIBUTING.md`, keep each change focused, include tests, and make sure
ruff (lint + format) and the pytest suite pass before proposing a merge. Do not
add secrets, credentials, or personal data.

## See also

- `README.md` — overview, adapter status, and usage
- `CONTRIBUTING.md` — contribution workflow and CLA
- `SECURITY.md` — reporting security vulnerabilities
