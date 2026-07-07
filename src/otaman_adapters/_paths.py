"""Shared path-safety guard for filesystem operations keyed by skill name.

Skill names originate from SKILL.md frontmatter (untrusted content — a skill
pack may be third-party or compromised) but are used to build filesystem
paths for writing and deleting files (see ``claude_code.py``, ``gemini.py``).
``safe_child_path`` is the single choke point that confines those paths to
the intended root directory.
"""
from __future__ import annotations

from pathlib import Path


class UnsafeSkillNameError(ValueError):
    """Raised when a skill name would escape its intended root directory."""


def validate_skill_name_shape(name: str) -> None:
    """Reject a skill name that could never be a safe single path component.

    Catches the traversal shapes (empty, ``.``/``..``, path separators,
    absolute paths) that are unsafe regardless of which root they'd be
    joined against. Does not require a root directory to exist, so this is
    usable at parse time (:func:`otaman_adapters.loader.load_skill`) before
    a target directory is even known.
    """
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise UnsafeSkillNameError(f"unsafe skill name: {name!r}")


def safe_child_path(root: Path, name: str) -> Path:
    """Return ``root / name``, guaranteed to resolve inside ``root``.

    Rejects (raises :class:`UnsafeSkillNameError`) any ``name`` that fails
    :func:`validate_skill_name_shape`, or whose resolved path escapes
    ``root`` (e.g. via a pre-existing symlink). Rejecting outright rather
    than sanitizing avoids silently masking a malicious or malformed name
    behind a different, possibly colliding, path.
    """
    validate_skill_name_shape(name)

    resolved_root = root.resolve()
    resolved_candidate = (root / name).resolve()
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise UnsafeSkillNameError(f"unsafe skill name: {name!r}")

    return root / name
