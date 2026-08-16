"""OpenAI Agents SDK adapter for SKILL.md-based skills.

The OpenAI Agents SDK (openai-agents-python) does not have a native SKILL.md
discovery mechanism.  Skill activation in this runtime happens at *instruction
injection time*: the agent's `instructions` string is built to include each
active skill's description + trigger cues so the model knows when to adopt the
skill's persona/methodology.

This adapter's jobs are:
  1. Format each active skill's frontmatter into an instructions block.
  2. Inject a caveat annotation into the description for `partial` skills.
  3. Skip `unsupported` skills entirely.
  4. Write two output files to `target_dir/`:
       - ``skills_block.md``   — human-readable markdown instructions fragment
       - ``skills_block.py``   — importable Python constant ``SKILL_INSTRUCTIONS``
     These are consumed by the runner that constructs the Agent instance.

Usage example (runtime integration):
    from skills_block import SKILL_INSTRUCTIONS
    from agents import Agent

    agent = Agent(
        name="otaman-agent",
        instructions=SKILL_INSTRUCTIONS + "\\n\\n" + BASE_INSTRUCTIONS,
    )
"""

from __future__ import annotations

from pathlib import Path

from .capabilities import AdapterCapabilities, DataClassification
from .models import CompatibilityLevel, RegistrationResult, Skill

_RUNTIME_ID = "openai-agents"

# Template for each skill block inside the instructions fragment.
_SKILL_TEMPLATE = """\
### {name}

{description}
{triggers_section}"""

_HEADER = """\
## Active Skills

The following skills are available to you.  When user input matches a skill's
trigger cues, adopt that skill's methodology and persona for the response.

---
"""

_SEPARATOR = "\n---\n"


class OpenAIAgentsAdapter:
    """Register SKILL.md skills with the OpenAI Agents SDK runtime.

    Produces two files in ``target_dir/``:

    * ``skills_block.md``  — markdown fragment ready to paste / include in docs.
    * ``skills_block.py``  — Python module exporting ``SKILL_INSTRUCTIONS: str``
      and ``REGISTERED_SKILLS: list[str]`` for programmatic use by the runner.

    Returns one :class:`RegistrationResult` per input skill.
    """

    runtime_id = _RUNTIME_ID

    # Compliance posture: default backend is plain OpenAI API (api.openai.com),
    # which does not offer a HIPAA BAA or PCI-DSS certification.  INTERNAL and
    # SENSITIVE data can be routed here by default.  PHI and REGULATED require
    # an operator to configure an Azure OpenAI endpoint with a Microsoft BAA —
    # not the default — matching the default-posture convention used by
    # ClaudeCodeAdapter and GeminiCliAdapter/GeminiApiAdapter.
    capabilities: AdapterCapabilities = AdapterCapabilities.for_levels(
        DataClassification.INTERNAL,
        DataClassification.SENSITIVE,
        notes=(
            "Default: plain OpenAI API (api.openai.com, no BAA). "
            "INTERNAL + SENSITIVE cleared. PHI/REGULATED require Azure OpenAI "
            "with a Microsoft BAA (operator-configured, not default)."
        ),
    )

    def register(
        self,
        skills: list[Skill],
        target_dir: Path,
    ) -> list[RegistrationResult]:
        """Render active skills to an instructions block in ``target_dir/``."""
        target_dir.mkdir(parents=True, exist_ok=True)

        results: list[RegistrationResult] = []
        blocks: list[str] = []
        registered_names: list[str] = []

        for skill in skills:
            compat = skill.compatibility_for(_RUNTIME_ID)

            if compat == CompatibilityLevel.UNSUPPORTED:
                results.append(
                    RegistrationResult(
                        skill_name=skill.name,
                        registered=False,
                        target_path=None,
                        compatibility=compat,
                        reason=f"provider_support[{_RUNTIME_ID}] = unsupported",
                    )
                )
                continue

            caveat: str | None = None
            if compat == CompatibilityLevel.PARTIAL:
                caveat = skill.notes_for(_RUNTIME_ID)

            block = _render_skill_block(skill, caveat)
            blocks.append(block)
            registered_names.append(skill.name)
            results.append(
                RegistrationResult(
                    skill_name=skill.name,
                    registered=True,
                    target_path=target_dir / "skills_block.md",
                    compatibility=compat,
                    caveat=caveat,
                )
            )

        instructions = _build_instructions(blocks)
        _write_outputs(target_dir, instructions, registered_names)

        return results

    def unregister(self, skill_names: list[str], target_dir: Path) -> None:
        """Remove adapter output files from ``target_dir/``.

        ``skill_names`` is accepted for interface consistency but ignored —
        the adapter produces single aggregate files, not one file per skill.
        If no skills remain (caller passes all registered names), both output
        files are removed.
        """
        for fname in ("skills_block.md", "skills_block.py"):
            p = target_dir / fname
            if p.exists():
                p.unlink()

    def build_instructions(self, skills: list[Skill]) -> str:
        """Return the instructions string without writing any files.

        Convenience method for callers that prefer to receive the text
        directly rather than via the filesystem.

        >>> adapter = OpenAIAgentsAdapter()
        >>> instructions = adapter.build_instructions(skills)
        >>> agent = Agent(name="x", instructions=instructions + base)
        """
        blocks: list[str] = []
        for skill in skills:
            compat = skill.compatibility_for(_RUNTIME_ID)
            if compat == CompatibilityLevel.UNSUPPORTED:
                continue
            caveat = skill.notes_for(_RUNTIME_ID) if compat == CompatibilityLevel.PARTIAL else None
            blocks.append(_render_skill_block(skill, caveat))
        return _build_instructions(blocks)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_skill_block(skill: Skill, caveat: str | None) -> str:
    """Format a single skill's frontmatter into a markdown skill block."""
    description = skill.description
    if caveat:
        description = f"{description} [CAVEAT: {caveat}]"

    # Build trigger list from frontmatter if present.
    raw_triggers = skill.raw_frontmatter.get("triggers") or []
    if raw_triggers:
        trigger_lines = "\n".join(f'- "{t}"' for t in raw_triggers)
        triggers_section = f"\n**Trigger cues** (activate when input includes):\n{trigger_lines}"
    else:
        triggers_section = ""

    return _SKILL_TEMPLATE.format(
        name=skill.name,
        description=description,
        triggers_section=triggers_section,
    )


def _build_instructions(blocks: list[str]) -> str:
    """Join rendered skill blocks into the full instructions fragment."""
    if not blocks:
        return ""
    return _HEADER + _SEPARATOR.join(blocks)


def _write_outputs(
    target_dir: Path,
    instructions: str,
    registered_names: list[str],
) -> None:
    """Write ``skills_block.md`` and ``skills_block.py`` to ``target_dir``."""
    md_path = target_dir / "skills_block.md"
    py_path = target_dir / "skills_block.py"

    md_path.write_text(instructions, encoding="utf-8")

    # Escape backslashes + triple-quotes for embedding in a Python string.
    escaped = instructions.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    names_repr = repr(registered_names)

    py_content = f'''\
"""Auto-generated by OpenAIAgentsAdapter — do not edit manually.

Usage::

    from skills_block import SKILL_INSTRUCTIONS, REGISTERED_SKILLS
    from agents import Agent

    agent = Agent(
        name="otaman-agent",
        instructions=SKILL_INSTRUCTIONS + "\\\\n\\\\n" + YOUR_BASE_INSTRUCTIONS,
    )
"""

REGISTERED_SKILLS: list[str] = {names_repr}

SKILL_INSTRUCTIONS: str = """\\
{escaped}"""
'''
    py_path.write_text(py_content, encoding="utf-8")
