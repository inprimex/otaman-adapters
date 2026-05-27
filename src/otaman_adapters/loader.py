from pathlib import Path

import yaml

from .models import CompatibilityLevel, Skill


def load_skill(skill_path: Path) -> Skill:
    """Parse a SKILL.md file into a Skill dataclass."""
    content = skill_path.read_text(encoding="utf-8")

    if not content.startswith("---"):
        raise ValueError(f"No YAML frontmatter found in {skill_path}")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Malformed frontmatter (missing closing ---) in {skill_path}")

    frontmatter = yaml.safe_load(parts[1])
    if not isinstance(frontmatter, dict):
        raise ValueError(f"Frontmatter did not parse as a mapping in {skill_path}")

    if "name" not in frontmatter:
        raise ValueError(f"Frontmatter missing required 'name' field in {skill_path}")

    provider_support: dict[str, CompatibilityLevel] = {}
    for runtime, level in (frontmatter.get("provider_support") or {}).items():
        try:
            provider_support[runtime] = CompatibilityLevel(level)
        except ValueError:
            provider_support[runtime] = CompatibilityLevel.UNTESTED

    return Skill(
        name=frontmatter["name"],
        description=frontmatter.get("description", ""),
        source_path=skill_path,
        provider_support=provider_support,
        provider_notes=dict(frontmatter.get("provider_notes") or {}),
        raw_frontmatter=frontmatter,
    )
