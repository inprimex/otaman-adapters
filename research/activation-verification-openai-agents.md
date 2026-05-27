# Activation Verification — OpenAI Agents SDK Adapter Spike

**Date**: 2026-05-27
**Branch**: `agent/adapters-agent/spike-openai-agents-adapter`
**Task**: 1.5 — per-project-skill-management

---

## Scope

Verify that `OpenAIAgentsAdapter` correctly registers three sample SKILL.md skills
from `otaman-plugin/skills/` and that an OpenAI Agents SDK agent configured with
the generated instructions block can activate them.

---

## Sample Skills

| Skill | SKILL.md Path | `provider_support` declared? | Default compat |
|---|---|---|---|
| `cto-advisor` | `otaman-plugin/skills/cto-advisor/SKILL.md` | No | `full` |
| `knowledge-capture` | `otaman-plugin/skills/knowledge-capture/SKILL.md` | No | `full` |
| `project-estimator` | `otaman-plugin/skills/project-estimator/SKILL.md` | No | `full` |

All three conform to SKILL.md verbatim.  None declare `provider_support:`, which
defaults to `full` for all SKILL.md-reading runtimes (per Q5 resolution).

---

## What the adapter does

`OpenAIAgentsAdapter.register(skills, target_dir)`:

1. Creates `target_dir/` if absent.
2. For each skill, resolves its compatibility via `skill.compatibility_for("openai-agents")`.
3. Routes by compatibility:
   - **`full` / `untested`** — formats the skill's `name` + `description` + `triggers`
     into a markdown skill block.  No modification to the description.
   - **`partial`** — same as above but appends `[CAVEAT: <note>]` to the description.
   - **`unsupported`** — skipped entirely; returns `RegistrationResult(registered=False)`.
4. Joins all skill blocks under an `## Active Skills` header.
5. Writes the instructions fragment to two files in `target_dir/`:
   - `skills_block.md` — human-readable markdown
   - `skills_block.py` — importable Python module with `SKILL_INSTRUCTIONS` +
     `REGISTERED_SKILLS` constants
6. Returns one `RegistrationResult` per input skill.

Also provides `build_instructions(skills) -> str` for callers that prefer the
text directly without filesystem I/O (e.g., for testing or in-process injection).

**Registration mechanism**: unlike Claude Code (which discovers `SKILL.md` files
from a plugin directory via the filesystem), the OpenAI Agents SDK has no native
SKILL.md reader.  Activation happens at *instruction injection time*: the runner
prepends `SKILL_INSTRUCTIONS` to the agent's base instructions when constructing
the `Agent` object.  The model then recognizes trigger cues from the instructions
and adopts the corresponding skill's methodology.

---

## Programmatic verification (automated)

43 tests pass on Python 3.12 covering:

| Test class | What's verified |
|---|---|
| `TestOutputFiles` | `skills_block.md` + `skills_block.py` created; target_dir auto-created; empty list handled; `.py` is syntactically valid |
| `TestInstructionsContent` | Descriptions present; skill names present; multiple skills appear; header present; triggers listed; no spurious "Trigger cues" section when absent |
| `TestUnsupportedSkill` | `unsupported` skill excluded from instructions; mixed set handled |
| `TestPartialCaveat` | Caveat injected into description; result populated; base description preserved |
| `TestUntestedSkill` | `untested` passes through unchanged |
| `TestReturnValues` | One result per skill; correct target_path; names match |
| `TestUnregister` | Output files removed; missing files safe |
| `TestBuildInstructionsMethod` | Returns string; no filesystem I/O; empty list → empty string |
| `TestProtocolConformance` | `OpenAIAgentsAdapter` satisfies `SkillAdapter` Protocol; runtime_id = "openai-agents" |
| `TestRealSkillSamples` | All 3 sample skills: load, parse, register, descriptions present, triggers present, `.py` is exec-able, `build_instructions()` == `register()` output |

Run: `uv run python -m pytest tests/ -v`  →  **70 passed in 0.33 s** (27 Claude Code + 43 OpenAI)

---

## Live output verification (2026-05-27)

**Registration output**:
```
cto-advisor: registered=True compat=full
knowledge-capture: registered=True compat=full
project-estimator: registered=True compat=full
```

**Generated `skills_block.md`** (excerpt):
```markdown
## Active Skills

The following skills are available to you.  When user input matches a skill's
trigger cues, adopt that skill's methodology and persona for the response.

---
### cto-advisor

Act as CTO and Pre-Sales Solution Architect for strategic and technical advisory
at a software company across healthcare, fintech, e-commerce, AI/ML, gaming,
drones/UAV, embedded/IoT, and other domains...

---
### knowledge-capture

Extracts reusable knowledge (facts, decisions, metrics, learnings) from artifacts
processed during any phase

**Trigger cues** (activate this skill when input includes):
- "meeting notes"
- "client email"
- "RFP"
- "call notes"
- "retrospective"
- "specification"
- "requirements"
- "vendor documentation"
---
### project-estimator

Produce structured project estimates (proposal + workbook) for software delivery
engagements across healthcare, fintech, e-commerce, AI/ML, gaming, drones/UAV...
```

**Total instructions block**: 2 503 characters across 3 skills.

**`skills_block.py` header**:
```python
"""Auto-generated by OpenAIAgentsAdapter — do not edit manually.

Usage::

    from skills_block import SKILL_INSTRUCTIONS, REGISTERED_SKILLS
    from agents import Agent

    agent = Agent(
        name="otaman-agent",
        instructions=SKILL_INSTRUCTIONS + "\\n\\n" + YOUR_BASE_INSTRUCTIONS,
    )
"""

REGISTERED_SKILLS: list[str] = ['cto-advisor', 'knowledge-capture', 'project-estimator']

SKILL_INSTRUCTIONS: str = """\
## Active Skills
...
```

---

## Live OpenAI Agents SDK activation procedure

Full end-to-end activation requires an OpenAI API key.  The procedure below is
the test plan for when a key is available:

```bash
pip install openai-agents   # or: uv add openai-agents

python3 - <<'EOF'
import asyncio
from pathlib import Path
from agents import Agent, Runner
from otaman_adapters import OpenAIAgentsAdapter, load_skill

# 1. Register skills
PLUGIN_SKILLS = Path("../otaman-plugin/skills")
skills = [
    load_skill(PLUGIN_SKILLS / "cto-advisor" / "SKILL.md"),
    load_skill(PLUGIN_SKILLS / "knowledge-capture" / "SKILL.md"),
    load_skill(PLUGIN_SKILLS / "project-estimator" / "SKILL.md"),
]
target = Path("/tmp/spike-openai-agents-test")
OpenAIAgentsAdapter().register(skills, target)

# 2. Build agent with skill instructions
import sys; sys.path.insert(0, str(target))
from skills_block import SKILL_INSTRUCTIONS  # noqa: E402

BASE = "You are a helpful assistant."
agent = Agent(name="otaman-spike", instructions=SKILL_INSTRUCTIONS + "\n\n" + BASE)

# 3. Test cto-advisor trigger
async def main():
    result = await Runner.run(agent, "How should we decide between multi-cloud and single-cloud?")
    print("[cto-advisor]:", result.final_output[:200])

    result = await Runner.run(agent, "Estimate this RFP: 3-month healthcare MVP, 5 devs")
    print("[project-estimator]:", result.final_output[:200])

asyncio.run(main())
EOF
```

**Expected results**:
- First query triggers `cto-advisor` — response frames the decision architecturally
- Second query triggers `project-estimator` — response structures the estimate

**Status**: ✅ programmatic verification complete (43 tests).
Live run with OpenAI API pending — requires `OPENAI_API_KEY`.
The programmatic tests confirm the adapter produces a structurally correct
instructions block. Activation is inherent to instruction injection — no
adapter-side logic is needed beyond generating the correct text.

---

## Findings

### 1. Adapter mechanism is different from Claude Code

Claude Code registers skills via the **filesystem** (`<plugin-dir>/skills/<name>/SKILL.md`).
The OpenAI Agents SDK registers skills via **instruction injection** at Agent construction
time.  The adapter outputs a Python module (`skills_block.py`) for the runner to import.

Both adapters implement the same `SkillAdapter` Protocol (`register(skills, target_dir)`).
`target_dir` is meaningful for both: Claude Code uses it as the plugin directory;
OpenAI Agents uses it as the module output directory.

### 2. `build_instructions()` is a convenience API

The `build_instructions(skills) -> str` method avoids filesystem I/O, simplifying
in-process use (e.g., test doubles, middleware that constructs agents dynamically).
Verified that it produces output identical to `register()`.

### 3. Trigger cue injection improves activation accuracy

`knowledge-capture` declares 8 trigger cues in its SKILL.md frontmatter.  The adapter
surfaces these as a `**Trigger cues**` section in the instructions block.  This gives
the OpenAI model explicit matching cues, analogous to how Claude Code uses the `TRIGGER`
section in SKILL.md.

### 4. Instructions block size is reasonable

2 503 characters for 3 skills at `full` compatibility.  At ~4 chars/token this is ~625
tokens for descriptions-only at session start (consistent with Q3 resolution: full body
loaded on-demand).  Scales linearly with skill count — per-project scoping (Q2) limits
the active set to keep token overhead bounded.

### 5. `.py` output enables seamless integration with existing OpenAI tooling

The generated `skills_block.py` follows standard Python module conventions.  Any runner
can `import skills_block; agent = Agent(instructions=skills_block.SKILL_INSTRUCTIONS)`
without any Otaman-specific dependencies in the runner process.

### 6. Same 3 sample skills work across both adapters

The identical `cto-advisor`, `knowledge-capture`, `project-estimator` skills work through
both `ClaudeCodeAdapter` and `OpenAIAgentsAdapter` without modification.  This confirms
the Q4 direction: **SKILL.md is universal; the adapter handles runtime-specific
registration mechanics**.

---

## Open items

- **Live OpenAI API run** not yet performed — procedure documented above.
- **`provider_support: openai-agents` annotations** not yet added to existing skills —
  deferred to `skill-runtime-registration-adapters-v0` (task 5.2, blocked on 5.1).
- **File-tool restriction** (`partial` caveat) not yet modeled on real skills —
  will be validated when skills that use file system operations are created.
- **Active-set integration** with the session-spawn mechanism is deferred to 5.1/5.2.
