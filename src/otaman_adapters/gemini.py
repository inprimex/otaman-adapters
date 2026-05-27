"""Gemini adapter sketch for SKILL.md-based skills.

**Status**: Sketch — not production-ready.  Written for task 1.6 of
``per-project-skill-management`` to identify Gemini-specific limitations and
confirm which skill capabilities map cleanly.

## Two Gemini runtimes

There are two distinct Gemini-family runtimes that would use this adapter:

### 1. Gemini CLI (``gemini-cli``)
Google's open-source Claude Code equivalent (released 2025, part of the
SKILL.md cross-LLM standard: Anthropic + OpenAI + Cursor + Gemini CLI +
Windsurf + Grok Build).  Reads SKILL.md natively.  The registration mechanism
is **identical to Claude Code**: place ``<plugin-dir>/skills/<name>/SKILL.md``.

### 2. Gemini API / Vertex AI Agents
Programmatic runtime (``google-generativeai`` SDK).  No native SKILL.md reader.
Registration mechanism is **identical to OpenAI Agents**: instruction injection
(prepend skill descriptions to the system instruction string).

## This module

Provides ``GeminiCliAdapter`` (file-based, reuses the same layout as
``ClaudeCodeAdapter``) and ``GeminiApiAdapter`` (instruction-based, reuses the
same text-generation approach as ``OpenAIAgentsAdapter``).

## Known Gemini-specific limitations

See ``research/gemini-adapter-limitations.md`` for the full analysis.
Summary:

| Capability | Gemini CLI | Gemini API |
|---|---|---|
| SKILL.md native reading | ✅ full | ❌ not supported (inject via system instruction) |
| System instructions | ✅ full | ✅ full |
| Trigger cues in instructions | ✅ full | ✅ full |
| Multi-turn memory | ✅ full | ⚠️ partial (stateless per-request without explicit history) |
| Computer-use tools | ❌ unsupported | ❌ unsupported |
| File system tools | ⚠️ partial (Gemini CLI: limited scope vs Claude Code) | ❌ unsupported |
| MCP server binding | ⚠️ partial (Gemini CLI supports MCP, subset of tools) | ❌ unsupported |
| Function calling | ✅ full (both runtimes) | ✅ full |
"""
from __future__ import annotations

import shutil
import re
from pathlib import Path

from .models import CompatibilityLevel, RegistrationResult, Skill
from .openai_agents import (
    OpenAIAgentsAdapter,
    _build_instructions,
    _render_skill_block,
    _write_outputs,
)

_RUNTIME_ID_CLI = "gemini-cli"
_RUNTIME_ID_API = "gemini-api"


class GeminiCliAdapter:
    """Register SKILL.md skills with the Gemini CLI runtime.

    Gemini CLI reads SKILL.md natively (cross-LLM standard adopted Dec 2025).
    Registration is file-based: place each skill's SKILL.md at
    ``<target_dir>/skills/<name>/SKILL.md``.

    This is structurally identical to ``ClaudeCodeAdapter``; the difference is
    the ``runtime_id`` used for compatibility resolution.  Skills that declare::

        provider_support:
          gemini-cli: partial

    will have a ``[CAVEAT: …]`` injected into their ``description:`` field.

    Limitations vs Claude Code:
    - ``computer-use`` tool not available — skills requiring it should declare
      ``provider_support.gemini-cli: unsupported``.
    - MCP server binding: Gemini CLI supports MCP but the tool subset is narrower.
      Skills relying on specific MCP tools should declare ``partial`` and add a note.
    - File system access scope may differ; test per-skill.
    """

    runtime_id = _RUNTIME_ID_CLI

    def register(self, skills: list[Skill], target_dir: Path) -> list[RegistrationResult]:
        """Register active skills under target_dir/skills/<name>/SKILL.md."""
        skills_root = target_dir / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)

        results: list[RegistrationResult] = []
        for skill in skills:
            compat = skill.compatibility_for(_RUNTIME_ID_CLI)

            if compat == CompatibilityLevel.UNSUPPORTED:
                results.append(RegistrationResult(
                    skill_name=skill.name,
                    registered=False,
                    target_path=None,
                    compatibility=compat,
                    reason=f"provider_support[{_RUNTIME_ID_CLI}] = unsupported",
                ))
                continue

            skill_dir = skills_root / skill.name
            skill_dir.mkdir(parents=True, exist_ok=True)
            dest = skill_dir / "SKILL.md"

            if compat == CompatibilityLevel.PARTIAL:
                caveat = skill.notes_for(_RUNTIME_ID_CLI)
                dest.write_text(
                    _inject_caveat(skill.source_path.read_text(encoding="utf-8"), caveat),
                    encoding="utf-8",
                )
                results.append(RegistrationResult(
                    skill_name=skill.name,
                    registered=True,
                    target_path=dest,
                    compatibility=compat,
                    caveat=caveat,
                ))
            else:
                shutil.copy2(skill.source_path, dest)
                _copy_siblings(skill.source_path.parent, skill_dir)
                results.append(RegistrationResult(
                    skill_name=skill.name,
                    registered=True,
                    target_path=dest,
                    compatibility=compat,
                ))

        return results

    def unregister(self, skill_names: list[str], target_dir: Path) -> None:
        skills_root = target_dir / "skills"
        for name in skill_names:
            skill_dir = skills_root / name
            if skill_dir.exists():
                shutil.rmtree(skill_dir)


class GeminiApiAdapter:
    """Register SKILL.md skills with the Gemini API (google-generativeai SDK) runtime.

    Gemini API has no native SKILL.md reader.  Registration is via instruction
    injection: the adapter writes a ``skills_block.md`` and ``skills_block.py``
    (containing ``SKILL_INSTRUCTIONS``) to ``target_dir/``.

    Usage::

        import google.generativeai as genai
        from skills_block import SKILL_INSTRUCTIONS

        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=SKILL_INSTRUCTIONS + "\\n\\n" + BASE_INSTRUCTIONS,
        )

    This is structurally identical to ``OpenAIAgentsAdapter``; the difference is
    the ``runtime_id`` used for compatibility resolution.

    Limitations vs OpenAI Agents:
    - Multi-turn memory is stateless per request without explicit history passing.
      Skills that depend on conversation memory should declare ``partial``.
    - Computer-use and file system tools are unsupported via Gemini API.
    - MCP server binding is not available via Gemini API.
    """

    runtime_id = _RUNTIME_ID_API

    def register(
        self,
        skills: list[Skill],
        target_dir: Path,
    ) -> list[RegistrationResult]:
        """Render active skills to an instructions block in target_dir/."""
        target_dir.mkdir(parents=True, exist_ok=True)

        results: list[RegistrationResult] = []
        blocks: list[str] = []
        registered_names: list[str] = []

        for skill in skills:
            compat = skill.compatibility_for(_RUNTIME_ID_API)

            if compat == CompatibilityLevel.UNSUPPORTED:
                results.append(RegistrationResult(
                    skill_name=skill.name,
                    registered=False,
                    target_path=None,
                    compatibility=compat,
                    reason=f"provider_support[{_RUNTIME_ID_API}] = unsupported",
                ))
                continue

            caveat = skill.notes_for(_RUNTIME_ID_API) if compat == CompatibilityLevel.PARTIAL else None
            blocks.append(_render_skill_block(skill, caveat))
            registered_names.append(skill.name)
            results.append(RegistrationResult(
                skill_name=skill.name,
                registered=True,
                target_path=target_dir / "skills_block.md",
                compatibility=compat,
                caveat=caveat,
            ))

        instructions = _build_instructions(blocks)
        _write_outputs(target_dir, instructions, registered_names)
        return results

    def unregister(self, skill_names: list[str], target_dir: Path) -> None:
        for fname in ("skills_block.md", "skills_block.py"):
            p = target_dir / fname
            if p.exists():
                p.unlink()

    def build_instructions(self, skills: list[Skill]) -> str:
        """Return the instructions string without writing any files."""
        blocks = []
        for skill in skills:
            compat = skill.compatibility_for(_RUNTIME_ID_API)
            if compat == CompatibilityLevel.UNSUPPORTED:
                continue
            caveat = skill.notes_for(_RUNTIME_ID_API) if compat == CompatibilityLevel.PARTIAL else None
            blocks.append(_render_skill_block(skill, caveat))
        return _build_instructions(blocks)


# ---------------------------------------------------------------------------
# Helpers (shared with ClaudeCodeAdapter logic)
# ---------------------------------------------------------------------------

def _inject_caveat(content: str, caveat: str | None) -> str:
    """Append a [CAVEAT: …] note to the description field in frontmatter."""
    if not caveat:
        return content

    def _append(match: re.Match) -> str:
        desc = match.group(1)
        stripped = desc.strip().strip('"').strip("'")
        return f'description: "{stripped} [CAVEAT: {caveat}]"'

    pattern = r'description:\s*["\']?(.+?)["\']?\s*$'
    patched, n = re.subn(pattern, _append, content, count=1, flags=re.MULTILINE)
    if n == 0:
        patched = content.replace("---\n", f"---\n# CAVEAT ({_RUNTIME_ID_CLI}): {caveat}\n", 1)
    return patched


def _copy_siblings(source_dir: Path, dest_dir: Path) -> None:
    """Copy non-SKILL.md assets (references/, etc.) alongside the registered skill."""
    for item in source_dir.iterdir():
        if item.name == "SKILL.md":
            continue
        target = dest_dir / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
