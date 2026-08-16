# AdapterCapabilities Extension — Backward Compatibility Note (task 4.2)

**Author**: adapters-agent
**Date**: 2026-05-27
**Change**: otaman-router-v1-design

---

## What was added

`AdapterCapabilities` (new frozen dataclass) + `DataClassification` (new enum)
added to `src/otaman_adapters/capabilities.py`.

Each adapter gained a class-level `capabilities: AdapterCapabilities` attribute:
- `ClaudeCodeAdapter.capabilities`
- `OpenAIAgentsAdapter.capabilities`
- `GeminiCliAdapter.capabilities`
- `GeminiApiAdapter.capabilities`

---

## Compatibility verdict: ✅ fully backward-compatible

### 1. Existing tests — zero failures

All 70 pre-existing tests pass unchanged after the addition:

```
27 (ClaudeCodeAdapter) + 43 (OpenAIAgentsAdapter) = 70 passed, 0 failed
```

No test was modified. Adding a class attribute to an existing class does not
alter the class's existing interface.

### 2. `register()` / `unregister()` signatures unchanged

Both method signatures are identical before and after:

```python
# Before and after — unchanged
def register(self, skills: list[Skill], target_dir: Path) -> list[RegistrationResult]: ...
def unregister(self, skill_names: list[str], target_dir: Path) -> None: ...
```

### 3. `SkillAdapter` Protocol unchanged

The `SkillAdapter` Protocol in `adapter.py` was NOT extended with a `capabilities`
field in this change.  The Protocol still only requires `runtime_id`, `register`,
and `unregister`.

Protocol conformance tests continue to pass:
```
TestProtocolConformance::test_claude_code_adapter_satisfies_skill_adapter_protocol PASSED
TestProtocolConformance::test_openai_agents_adapter_satisfies_skill_adapter_protocol PASSED
```

### 4. `capabilities` is class-level (not instance-level)

The attribute is declared on the class body, not `__init__`.  Existing code that
constructs `ClaudeCodeAdapter()` without arguments is not affected.  The
attribute is inherited by all instances and shared (same object reference):

```python
a1, a2 = ClaudeCodeAdapter(), ClaudeCodeAdapter()
assert a1.capabilities is a2.capabilities is ClaudeCodeAdapter.capabilities  # True
```

Verified by `TestBackwardCompatibility::test_capabilities_is_class_level_not_instance_level`.

### 5. No new required imports in existing call sites

`AdapterCapabilities` and `DataClassification` are exported from
`otaman_adapters.__init__` but importing them is opt-in.  Existing code that
imports only `ClaudeCodeAdapter`, `load_skill`, etc. continues to work without
modification.

---

## Forward compatibility with core-agent task 1.4

When `otaman-core` publishes `otaman_core.routing` (core-agent task 1.4), the
migration is a one-line import swap in `capabilities.py`:

```python
# Before (local stub):
class DataClassification(str, Enum): ...


@dataclass(frozen=True)
class AdapterCapabilities: ...


# After (once core ships):
from otaman_core.routing import DataClassification, AdapterCapabilities
```

The adapter files (`claude_code.py`, `openai_agents.py`, `gemini.py`) do not
need to change — they import from `.capabilities`, not from `otaman_core` directly.
The re-export in `__init__.py` continues to work.

The `AdapterCapabilities` field names (`compliance`, `notes`) and the
`DataClassification` enum values (`internal`, `sensitive`, `pii`, `phi`,
`regulated`) are intentionally identical to the core definitions to make this
swap a no-op from the caller's perspective.

---

## Test coverage added (task 4.2 scope)

`tests/test_capabilities.py` — 40 new tests:

| Class | Tests | What |
|---|---|---|
| `TestDataClassification` | 3 | Enum values, string coercion, set membership |
| `TestAdapterCapabilities` | 6 | Constructor, `clears()`, empty, notes, immutability |
| `TestClaudeCodeAdapterCompliance` | 8 | Attribute presence, cleared/not-cleared per level, notes content |
| `TestOpenAIAgentsAdapterCompliance` | 7 | Same + PHI/REGULATED cleared, Azure mention |
| `TestGeminiCliAdapterCompliance` | 4 | Cleared/not-cleared |
| `TestGeminiApiAdapterCompliance` | 3 | Cleared/not-cleared |
| `TestBackwardCompatibility` | 4 | register() works, class-level attr, Protocol satisfied |

**Total post-addition**: 110 tests, 110 passed.
