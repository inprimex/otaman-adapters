"""Tests for F149: path traversal via unvalidated skill name.

Coverage:
  - `_paths.safe_child_path` / `validate_skill_name_shape` unit behavior
  - `load_skill` rejects unsafe names in SKILL.md frontmatter
  - ClaudeCodeAdapter/GeminiCliAdapter register() rejects unsafe names
    without blocking the rest of a mixed batch
  - ClaudeCodeAdapter/GeminiCliAdapter unregister() ignores unsafe names
    instead of deleting outside the skills root
"""
from pathlib import Path

import pytest

from otaman_adapters import ClaudeCodeAdapter, GeminiCliAdapter, load_skill
from otaman_adapters._paths import (
    UnsafeSkillNameError,
    safe_child_path,
    validate_skill_name_shape,
)
from otaman_adapters.models import Skill

UNSAFE_NAMES = [
    "../../etc/evil",
    "../escape",
    "/etc/passwd",
    "..",
    ".",
    "",
    "a/b",
    "a\\b",
]


def _write_skill(path: Path, name: str, description: str = "desc") -> Path:
    skill_path = path / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(f'---\nname: "{name}"\ndescription: "{description}"\n---\n\nbody\n')
    return skill_path


def _raw_skill(name: str, source_path: Path) -> Skill:
    """Construct a Skill bypassing load_skill's validation — simulates any
    non-loader code path that might hand an adapter an unvalidated name."""
    return Skill(name=name, description="desc", source_path=source_path)


# ---------------------------------------------------------------------------
# _paths.safe_child_path / validate_skill_name_shape
# ---------------------------------------------------------------------------

class TestSafeChildPath:
    @pytest.mark.parametrize("name", UNSAFE_NAMES)
    def test_rejects_unsafe_names(self, tmp_path, name):
        with pytest.raises(UnsafeSkillNameError):
            safe_child_path(tmp_path, name)

    def test_accepts_plain_name(self, tmp_path):
        result = safe_child_path(tmp_path, "my-skill")
        assert result == tmp_path / "my-skill"

    def test_rejects_symlink_escape(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / "evil").symlink_to(outside, target_is_directory=True)

        with pytest.raises(UnsafeSkillNameError):
            safe_child_path(root, "evil")

    @pytest.mark.parametrize("name", UNSAFE_NAMES)
    def test_validate_skill_name_shape_rejects(self, name):
        with pytest.raises(UnsafeSkillNameError):
            validate_skill_name_shape(name)

    def test_validate_skill_name_shape_accepts_plain_name(self):
        validate_skill_name_shape("my-skill")  # no raise


# ---------------------------------------------------------------------------
# load_skill — rejects unsafe names at parse time
# ---------------------------------------------------------------------------

class TestLoadSkillRejectsUnsafeNames:
    def test_traversal_name_raises(self, tmp_path):
        p = _write_skill(tmp_path / "src", "../../etc/evil")
        with pytest.raises(ValueError, match="[Uu]nsafe"):
            load_skill(p)

    def test_absolute_name_raises(self, tmp_path):
        p = _write_skill(tmp_path / "src", "/etc/passwd")
        with pytest.raises(ValueError, match="[Uu]nsafe"):
            load_skill(p)


# ---------------------------------------------------------------------------
# ClaudeCodeAdapter — register()/unregister() defense in depth
# ---------------------------------------------------------------------------

class TestClaudeCodeAdapterRejectsUnsafeNames:
    @pytest.mark.parametrize("name", ["../../etc/evil", "/etc/passwd", ".."])
    def test_register_rejects_unsafe_name(self, tmp_path, name):
        source = _write_skill(tmp_path / "src", "placeholder")
        skill = _raw_skill(name, source)
        target = tmp_path / "plugin"

        results = ClaudeCodeAdapter().register([skill], target)

        assert results[0].registered is False
        assert "unsafe" in results[0].reason.lower()
        # Nothing was written outside the intended skills root.
        assert not (tmp_path / "etc").exists()
        assert not Path("/etc/evil").exists()

    def test_mixed_batch_unsafe_name_does_not_block_others(self, tmp_path):
        src = tmp_path / "src"
        good_source = _write_skill(src / "good", "good-skill")
        good = _raw_skill("good-skill", good_source)
        bad = _raw_skill("../../evil", good_source)

        target = tmp_path / "plugin"
        results = ClaudeCodeAdapter().register([good, bad], target)

        by_name = {r.skill_name: r for r in results}
        assert by_name["good-skill"].registered is True
        assert (target / "skills" / "good-skill" / "SKILL.md").exists()
        assert by_name["../../evil"].registered is False

    def test_unregister_ignores_unsafe_name(self, tmp_path):
        target = tmp_path / "plugin"
        canary_dir = tmp_path / "canary"
        canary_dir.mkdir()
        (canary_dir / "keepme.txt").write_text("do not delete")

        # Traversal name crafted to reach the canary dir from skills_root.
        traversal_name = "../../canary"
        adapter = ClaudeCodeAdapter()
        adapter.unregister([traversal_name], target)

        assert (canary_dir / "keepme.txt").exists()


# ---------------------------------------------------------------------------
# GeminiCliAdapter — same defense in depth
# ---------------------------------------------------------------------------

class TestGeminiCliAdapterRejectsUnsafeNames:
    @pytest.mark.parametrize("name", ["../../etc/evil", "/etc/passwd", ".."])
    def test_register_rejects_unsafe_name(self, tmp_path, name):
        source = _write_skill(tmp_path / "src", "placeholder")
        skill = _raw_skill(name, source)
        target = tmp_path / "plugin"

        results = GeminiCliAdapter().register([skill], target)

        assert results[0].registered is False
        assert "unsafe" in results[0].reason.lower()
        assert not (tmp_path / "etc").exists()

    def test_mixed_batch_unsafe_name_does_not_block_others(self, tmp_path):
        src = tmp_path / "src"
        good_source = _write_skill(src / "good", "good-skill")
        good = _raw_skill("good-skill", good_source)
        bad = _raw_skill("/etc/passwd", good_source)

        target = tmp_path / "plugin"
        results = GeminiCliAdapter().register([good, bad], target)

        by_name = {r.skill_name: r for r in results}
        assert by_name["good-skill"].registered is True
        assert (target / "skills" / "good-skill" / "SKILL.md").exists()
        assert by_name["/etc/passwd"].registered is False

    def test_unregister_ignores_unsafe_name(self, tmp_path):
        target = tmp_path / "plugin"
        canary_dir = tmp_path / "canary"
        canary_dir.mkdir()
        (canary_dir / "keepme.txt").write_text("do not delete")

        adapter = GeminiCliAdapter()
        adapter.unregister(["../../canary"], target)

        assert (canary_dir / "keepme.txt").exists()
