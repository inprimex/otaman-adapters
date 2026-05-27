from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class CompatibilityLevel(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    UNTESTED = "untested"
    UNSUPPORTED = "unsupported"


@dataclass
class Skill:
    name: str
    description: str
    source_path: Path
    provider_support: dict[str, CompatibilityLevel] = field(default_factory=dict)
    provider_notes: dict[str, str] = field(default_factory=dict)
    raw_frontmatter: dict = field(default_factory=dict)

    def compatibility_for(self, runtime: str) -> CompatibilityLevel:
        return self.provider_support.get(runtime, CompatibilityLevel.FULL)

    def notes_for(self, runtime: str) -> Optional[str]:
        return self.provider_notes.get(runtime)


@dataclass
class RegistrationResult:
    skill_name: str
    registered: bool
    target_path: Optional[Path]
    compatibility: CompatibilityLevel
    caveat: Optional[str] = None
    reason: Optional[str] = None
