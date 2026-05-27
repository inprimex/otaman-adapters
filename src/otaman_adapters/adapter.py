from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import RegistrationResult, Skill


@runtime_checkable
class SkillAdapter(Protocol):
    """Contract every runtime adapter must satisfy."""

    runtime_id: str

    def register(self, skills: list[Skill], target_dir: Path) -> list[RegistrationResult]:
        """Place skills into target_dir so the runtime can discover them.

        Args:
            skills: Active skill set resolved by the platform (per-project scoping).
            target_dir: Root of the runtime's skills directory (e.g. <plugin-dir>/skills/).

        Returns:
            One RegistrationResult per input skill.
        """
        ...

    def unregister(self, skill_names: list[str], target_dir: Path) -> None:
        """Remove previously registered skills from target_dir."""
        ...
