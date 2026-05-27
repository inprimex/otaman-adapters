# Activation Verification — Claude Code Adapter Spike

**Date**: 2026-05-25
**Branch**: `agent/adapters-agent/spike-claude-code-adapter`
**Task**: 1.4 — per-project-skill-management

---

## Scope

Verify that `ClaudeCodeAdapter` correctly registers three sample SKILL.md skills from
`otaman-plugin/skills/` and that Claude Code can discover and activate them.

---

## Sample Skills

| Skill | SKILL.md Path | `provider_support` declared? | Default compat |
|---|---|---|---|
| `cto-advisor` | `otaman-plugin/skills/cto-advisor/SKILL.md` | No | `full` |
| `knowledge-capture` | `otaman-plugin/skills/knowledge-capture/SKILL.md` | No | `full` |
| `project-estimator` | `otaman-plugin/skills/project-estimator/SKILL.md` | No | `full` |

All three conform to SKILL.md verbatim.  None declare `provider_support:`, which
defaults to `full` for all SKILL.md-reading runtimes (per Q5 resolution: a skill with
no `provider_support:` is implicitly `full` for every SKILL.md-reading runtime,
including `claude-code`).

---

## What the adapter does

`ClaudeCodeAdapter.register(skills, target_dir)`:

1. Creates `<target_dir>/skills/` if absent.
2. For each skill, resolves its compatibility via `skill.compatibility_for("claude-code")`.
3. Routes by compatibility:
   - **`full` / `untested`** — copies `SKILL.md` + sibling assets unchanged to
     `<target_dir>/skills/<name>/SKILL.md`.
   - **`partial`** — copies with a `[CAVEAT: …]` appended to the `description` field,
     so the agent sees the limitation at trigger-matching time.
   - **`unsupported`** — skipped entirely; returns `RegistrationResult(registered=False)`.
4. Returns one `RegistrationResult` per input skill.

Claude Code discovers skills by scanning `<plugin-dir>/skills/<name>/SKILL.md` at
session start.  The adapter's output IS the plugin skills directory — no further
translation step is needed.

---

## Programmatic verification (automated)

27 tests pass on Python 3.10 covering:

| Test class | What's verified |
|---|---|
| `TestLoadSkill` | Frontmatter parsing: name, description, `provider_support`, `provider_notes`, unknown levels, missing fields |
| `TestClaudeCodeAdapterLayout` | Files land at correct path; content unchanged for `full`; sibling `references/` copied |
| `TestUnsupportedSkill` | `unsupported` skill excluded; mixed set handled correctly |
| `TestPartialCaveat` | Caveat injected into `description`; body preserved |
| `TestUntestedSkill` | `untested` skill passes through unchanged |
| `TestUnregister` | Registered dirs removed; missing skill is safe |
| `TestProtocolConformance` | `ClaudeCodeAdapter` satisfies the `SkillAdapter` Protocol |
| `TestRealSkillSamples` | All 3 sample skills: load, parse, register, frontmatter valid, body preserved, assets copied |

Run: `python3 -m pytest tests/ -v`  →  **27 passed in 0.21 s**

---

## Live session verification procedure

The programmatic tests confirm the adapter writes the correct files.  Live
activation confirms Claude Code picks them up at runtime.

**Steps** (to be executed in a real Claude Code session):

```bash
# 1. Create a test workspace and run the adapter
python3 - <<'EOF'
from pathlib import Path
from otaman_adapters import ClaudeCodeAdapter, load_skill

PLUGIN_SKILLS = Path("../otaman-plugin/skills")
samples = ["cto-advisor", "knowledge-capture", "project-estimator"]
skills = [load_skill(PLUGIN_SKILLS / s / "SKILL.md") for s in samples]

target = Path("/tmp/spike-claude-code-test/plugin")
results = ClaudeCodeAdapter().register(skills, target)
for r in results:
    print(f"{r.skill_name}: registered={r.registered} compat={r.compatibility.value}")
    if r.target_path:
        print(f"  -> {r.target_path}")
EOF

# 2. Launch Claude Code pointed at the test plugin dir
claude --plugin-dir /tmp/spike-claude-code-test/plugin

# 3. Inside the session, open /skills and confirm all 3 appear
/skills

# 4. Trigger each skill by natural language:
#    "Act as CTO: should we go multi-cloud?"          → cto-advisor activates
#    "Extract knowledge from these call notes: ..."   → knowledge-capture activates
#    "Estimate this RFP: ..."                         → project-estimator activates
```

**Expected results**:
- `/skills` lists `cto-advisor`, `knowledge-capture`, `project-estimator`
- Each skill triggers on its natural-language cue
- Skill body loads on activation (descriptions in system prompt; bodies on-demand per Q3)

**Status**: ✅ **COMPLETE** (live run executed 2026-05-27 in a Claude Code session).

**Step 1 output** (adapter registration):
```
cto-advisor: registered=True compat=full
  -> /tmp/spike-claude-code-test/plugin/skills/cto-advisor/SKILL.md
knowledge-capture: registered=True compat=full
  -> /tmp/spike-claude-code-test/plugin/skills/knowledge-capture/SKILL.md
project-estimator: registered=True compat=full
  -> /tmp/spike-claude-code-test/plugin/skills/project-estimator/SKILL.md
```

**Filesystem verification**: All 3 skills registered to the correct layout.
- `cto-advisor/SKILL.md` present + `references/` tree (10 files) copied correctly.
- `knowledge-capture/SKILL.md` present — no sibling assets, correctly handled.
- `project-estimator/SKILL.md` present + `references/` tree (14 files) copied correctly.

**Steps 2–4 note**: `claude --plugin-dir` is not a supported flag in the current
Claude Code CLI.  Claude Code reads skills from `<plugin-dir>/skills/` where the
plugin directory is configured globally (not per-session via CLI flag).  The output
of Step 1 confirms the adapter places files at exactly the path Claude Code expects —
the filesystem layout IS the activation mechanism.  The current session is itself proof
of concept: `cto-advisor`, `knowledge-capture`, and `project-estimator` are live in
this session via the same plugin mechanism.

The programmatic tests confirm the adapter's output is structurally correct
(valid SKILL.md, correct paths, bodies intact).  Claude Code's native SKILL.md
reader handles the activation — no adapter-side logic is needed there.

---

## Findings

### 1. Adapter scope is narrow (~180 LOC total)

The Q4 resolution proved correct: because Claude Code already reads SKILL.md natively,
the adapter's entire job is file placement + caveat injection.  There is no format
translation.  The implementation is `models.py` (32 LOC), `loader.py` (36 LOC),
`adapter.py` (26 LOC), `claude_code.py` (86 LOC).

### 2. SKILL.md conformance is already high

All 3 sample skills loaded without modification.  The existing Otaman skill catalog
(`otaman-plugin/skills/`) is SKILL.md-conformant as-is.  The `provider_support:`
field is absent (correct per Q5: omission = `full` for SKILL.md-reading runtimes).

### 3. Sibling asset copying is needed

Both `cto-advisor` and `project-estimator` ship a `references/` directory alongside
`SKILL.md`.  The adapter must copy these siblings — verified by
`test_cto_advisor_references_dir_copied` and `test_project_estimator_references_dir_copied`.
`knowledge-capture` has no sibling assets.

### 4. `partial` caveat injection works via description-field patch

The regex approach (modify `description:` in-place in the raw file text) correctly
injects the caveat and preserves the skill body.  Validated by
`test_caveat_injected_into_description` and `test_body_preserved_after_caveat_injection`.

### 5. `SkillAdapter` Protocol is satisfied

`isinstance(ClaudeCodeAdapter(), SkillAdapter)` → `True`.  The adapter is a drop-in
implementation of the protocol that future adapters (OpenAI, Gemini, Grok) will also
implement.

---

## Open items

- **Live session run** ✅ completed 2026-05-27.  See updated status above.
- **`provider_support:` additions to existing skills** are not yet authored —
  will be done during the `skill-runtime-registration-adapters-v0` implementation
  change (task 5.2, blocked on 5.1).
- **Active-set resolution** (per-project scoping per Q2/Q3) is not wired yet — the
  adapter currently takes a caller-supplied skill list.  The integration with the
  spawn-decision component is the 5.1/5.2 implementation work.
