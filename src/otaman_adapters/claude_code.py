import re
import shutil
from pathlib import Path

from .capabilities import AdapterCapabilities, DataClassification
from .models import CompatibilityLevel, RegistrationResult, Skill

# Claude Code discovers skills at <plugin-dir>/skills/<name>/SKILL.md.
# This adapter writes exactly that layout.  It does NOT translate the SKILL.md
# format — Claude Code reads SKILL.md natively.  The adapter's only jobs are:
#   1. Place each active skill's SKILL.md into the expected path.
#   2. Inject a caveat annotation into the description for `partial` skills.
#   3. Skip `unsupported` skills entirely.
#   4. Pass through `full` and `untested` skills unchanged.

_RUNTIME_ID = "claude-code"


class ClaudeCodeAdapter:
    runtime_id = _RUNTIME_ID

    # Compliance posture: Anthropic API (standard tier) does not offer a HIPAA
    # BAA or PCI-DSS certification by default.  Data classified INTERNAL or
    # SENSITIVE can be routed here.  PHI and REGULATED require an operator to
    # configure a Bedrock-Anthropic endpoint with an AWS BAA — not the default.
    capabilities: AdapterCapabilities = AdapterCapabilities.for_levels(
        DataClassification.INTERNAL,
        DataClassification.SENSITIVE,
        notes=(
            "Default: Anthropic API (no BAA).  INTERNAL + SENSITIVE cleared. "
            "PHI/REGULATED require Bedrock-Anthropic with AWS BAA (EE, operator-configured)."
        ),
    )

    def register(self, skills: list[Skill], target_dir: Path) -> list[RegistrationResult]:
        """Register active skills under target_dir/skills/<name>/SKILL.md."""
        skills_root = target_dir / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)

        results: list[RegistrationResult] = []
        for skill in skills:
            compat = skill.compatibility_for(_RUNTIME_ID)

            if compat == CompatibilityLevel.UNSUPPORTED:
                results.append(RegistrationResult(
                    skill_name=skill.name,
                    registered=False,
                    target_path=None,
                    compatibility=compat,
                    reason=f"provider_support[{_RUNTIME_ID}] = unsupported",
                ))
                continue

            skill_dir = skills_root / skill.name
            skill_dir.mkdir(parents=True, exist_ok=True)
            dest = skill_dir / "SKILL.md"

            if compat == CompatibilityLevel.PARTIAL:
                caveat = skill.notes_for(_RUNTIME_ID)
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
                # Copy any sibling assets (references/, etc.) the skill ships with.
                _copy_siblings(skill.source_path.parent, skill_dir)
                results.append(RegistrationResult(
                    skill_name=skill.name,
                    registered=True,
                    target_path=dest,
                    compatibility=compat,
                ))

        return results

    def unregister(self, skill_names: list[str], target_dir: Path) -> None:
        """Remove registered skill directories from target_dir/skills/."""
        skills_root = target_dir / "skills"
        for name in skill_names:
            skill_dir = skills_root / name
            if skill_dir.exists():
                shutil.rmtree(skill_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inject_caveat(content: str, caveat: str | None) -> str:
    """Append a [CAVEAT: …] note to the description field in frontmatter."""
    if not caveat:
        return content

    def _append(match: re.Match) -> str:
        desc = match.group(1)
        # Strip outer quotes if present so we can re-quote cleanly.
        stripped = desc.strip().strip('"').strip("'")
        return f'description: "{stripped} [CAVEAT: {caveat}]"'

    # Match: description: "…" or description: '…' or bare description: text
    pattern = r'description:\s*["\']?(.+?)["\']?\s*$'
    patched, n = re.subn(pattern, _append, content, count=1, flags=re.MULTILINE)
    if n == 0:
        # description field not found — append caveat as a comment after frontmatter open
        patched = content.replace("---\n", f"---\n# CAVEAT ({_RUNTIME_ID}): {caveat}\n", 1)
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
