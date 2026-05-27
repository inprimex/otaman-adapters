"""Spike: Claude Code adapter — activation-verification tests.

Coverage:
  - load_skill() parses SKILL.md frontmatter correctly
  - ClaudeCodeAdapter.register() places files at <target>/skills/<name>/SKILL.md
  - Full-compat skills are registered unchanged
  - Partial-compat skills get a caveat injected into the description
  - Unsupported skills are excluded from registration
  - Untested skills are registered with no modification
  - Sibling assets (references/) are copied alongside the skill
  - unregister() removes registered directories

The three sample skills (cto-advisor, knowledge-capture, project-estimator) are
loaded from the real otaman-plugin repo when it is present on disk (CI / dev
environments with the full polyrepo checkout).  Synthetic SKILL.md fixtures
cover all compatibility levels regardless of repo availability.
"""
import textwrap
from pathlib import Path

import pytest
import yaml

from otaman_adapters import ClaudeCodeAdapter, CompatibilityLevel, load_skill
from otaman_adapters.models import Skill

from conftest import CTO_ADVISOR_PATH, KNOWLEDGE_CAPTURE_PATH, PROJECT_ESTIMATOR_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_skill(path: Path, name: str, description: str, extra_frontmatter: str = "") -> Path:
    skill_path = path / name / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    extra = ("\n" + extra_frontmatter.strip()) if extra_frontmatter.strip() else ""
    skill_path.write_text(
        f"---\nname: {name}\ndescription: \"{description}\"{extra}\n---\n\n# {name} body\nThis is the skill body.\n"
    )
    return skill_path


# ---------------------------------------------------------------------------
# load_skill
# ---------------------------------------------------------------------------

class TestLoadSkill:
    def test_parses_name_and_description(self, tmp_path):
        p = _write_skill(tmp_path, "my-skill", "Does something useful")
        skill = load_skill(p)
        assert skill.name == "my-skill"
        assert skill.description == "Does something useful"

    def test_no_provider_support_defaults_empty(self, tmp_path):
        p = _write_skill(tmp_path, "bare", "No compat metadata")
        skill = load_skill(p)
        assert skill.provider_support == {}

    def test_parses_provider_support(self, tmp_path):
        extra = textwrap.dedent("""\
            provider_support:
              claude-code: full
              openai-agents: partial
              gemini: unsupported
        """)
        p = _write_skill(tmp_path, "multi-compat", "Multi-compat skill", extra)
        skill = load_skill(p)
        assert skill.compatibility_for("claude-code") == CompatibilityLevel.FULL
        assert skill.compatibility_for("openai-agents") == CompatibilityLevel.PARTIAL
        assert skill.compatibility_for("gemini") == CompatibilityLevel.UNSUPPORTED

    def test_missing_name_raises(self, tmp_path):
        bad = tmp_path / "bad" / "SKILL.md"
        bad.parent.mkdir(parents=True)
        bad.write_text("---\ndescription: no name here\n---\nbody\n")
        with pytest.raises(ValueError, match="name"):
            load_skill(bad)

    def test_no_frontmatter_raises(self, tmp_path):
        bad = tmp_path / "no-fm" / "SKILL.md"
        bad.parent.mkdir(parents=True)
        bad.write_text("Just a plain markdown file\n")
        with pytest.raises(ValueError, match="frontmatter"):
            load_skill(bad)

    def test_unknown_compat_level_falls_back_to_untested(self, tmp_path):
        extra = "provider_support:\n  some-runtime: experimental\n"
        p = _write_skill(tmp_path, "exp-skill", "Experimental", extra)
        skill = load_skill(p)
        assert skill.compatibility_for("some-runtime") == CompatibilityLevel.UNTESTED

    def test_default_compat_for_unknown_runtime_is_full(self, tmp_path):
        p = _write_skill(tmp_path, "default-compat", "No explicit support map")
        skill = load_skill(p)
        assert skill.compatibility_for("claude-code") == CompatibilityLevel.FULL
        assert skill.compatibility_for("any-unknown-runtime") == CompatibilityLevel.FULL


# ---------------------------------------------------------------------------
# ClaudeCodeAdapter — registration layout
# ---------------------------------------------------------------------------

class TestClaudeCodeAdapterLayout:
    def test_registered_skill_lands_at_expected_path(self, tmp_path):
        skill_path = _write_skill(tmp_path / "source", "alpha", "Alpha skill")
        skill = load_skill(skill_path)

        target = tmp_path / "plugin"
        adapter = ClaudeCodeAdapter()
        results = adapter.register([skill], target)

        assert len(results) == 1
        r = results[0]
        assert r.registered is True
        assert r.target_path == target / "skills" / "alpha" / "SKILL.md"
        assert r.target_path.exists()

    def test_full_compat_content_is_unchanged(self, tmp_path):
        skill_path = _write_skill(tmp_path / "src", "beta", "Beta skill")
        original = skill_path.read_text()
        skill = load_skill(skill_path)

        target = tmp_path / "plugin"
        ClaudeCodeAdapter().register([skill], target)

        registered = (target / "skills" / "beta" / "SKILL.md").read_text()
        assert registered == original

    def test_multiple_skills_all_registered(self, tmp_path):
        src = tmp_path / "src"
        skills = [
            load_skill(_write_skill(src, f"skill-{i}", f"Skill {i}"))
            for i in range(3)
        ]
        target = tmp_path / "plugin"
        results = ClaudeCodeAdapter().register(skills, target)

        assert all(r.registered for r in results)
        for i in range(3):
            assert (target / "skills" / f"skill-{i}" / "SKILL.md").exists()

    def test_sibling_references_dir_is_copied(self, tmp_path):
        src = tmp_path / "src" / "with-refs"
        src.mkdir(parents=True)
        skill_path = src / "SKILL.md"
        skill_path.write_text("---\nname: with-refs\ndescription: \"Has refs\"\n---\nbody\n")
        refs = src / "references"
        refs.mkdir()
        (refs / "data.md").write_text("# data")

        skill = load_skill(skill_path)
        target = tmp_path / "plugin"
        ClaudeCodeAdapter().register([skill], target)

        assert (target / "skills" / "with-refs" / "references" / "data.md").exists()


# ---------------------------------------------------------------------------
# Unsupported skills are excluded
# ---------------------------------------------------------------------------

class TestUnsupportedSkill:
    def test_unsupported_skill_not_registered(self, tmp_path):
        extra = "provider_support:\n  claude-code: unsupported\n"
        skill_path = _write_skill(tmp_path / "src", "no-go", "Unsupported", extra)
        skill = load_skill(skill_path)

        target = tmp_path / "plugin"
        results = ClaudeCodeAdapter().register([skill], target)

        r = results[0]
        assert r.registered is False
        assert r.target_path is None
        assert not (target / "skills" / "no-go").exists()

    def test_mixed_set_excludes_only_unsupported(self, tmp_path):
        src = tmp_path / "src"
        ok = load_skill(_write_skill(src, "ok-skill", "Fine"))
        bad_extra = "provider_support:\n  claude-code: unsupported\n"
        bad = load_skill(_write_skill(src, "bad-skill", "Bad", bad_extra))

        results = ClaudeCodeAdapter().register([ok, bad], tmp_path / "plugin")

        registered = {r.skill_name: r.registered for r in results}
        assert registered["ok-skill"] is True
        assert registered["bad-skill"] is False


# ---------------------------------------------------------------------------
# Partial compatibility — caveat injection
# ---------------------------------------------------------------------------

class TestPartialCaveat:
    def test_partial_skill_is_registered(self, tmp_path):
        extra = textwrap.dedent("""\
            provider_support:
              claude-code: partial
            provider_notes:
              claude-code: "computer-use unavailable; manual fallback required"
        """)
        skill_path = _write_skill(tmp_path / "src", "partial-skill", "Original desc", extra)
        skill = load_skill(skill_path)

        target = tmp_path / "plugin"
        results = ClaudeCodeAdapter().register([skill], target)

        r = results[0]
        assert r.registered is True
        assert r.compatibility == CompatibilityLevel.PARTIAL
        assert r.caveat == "computer-use unavailable; manual fallback required"

    def test_caveat_injected_into_description(self, tmp_path):
        extra = textwrap.dedent("""\
            provider_support:
              claude-code: partial
            provider_notes:
              claude-code: "needs human confirmation"
        """)
        skill_path = _write_skill(tmp_path / "src", "partial", "Do something", extra)
        skill = load_skill(skill_path)

        target = tmp_path / "plugin"
        ClaudeCodeAdapter().register([skill], target)

        content = (target / "skills" / "partial" / "SKILL.md").read_text()
        fm = yaml.safe_load(content.split("---", 2)[1])
        assert "needs human confirmation" in fm["description"]
        assert "CAVEAT" in fm["description"]

    def test_body_preserved_after_caveat_injection(self, tmp_path):
        extra = "provider_support:\n  claude-code: partial\n"
        skill_path = _write_skill(tmp_path / "src", "body-check", "Desc", extra)
        body_marker = "This is the skill body."
        skill = load_skill(skill_path)

        target = tmp_path / "plugin"
        ClaudeCodeAdapter().register([skill], target)

        content = (target / "skills" / "body-check" / "SKILL.md").read_text()
        assert body_marker in content


# ---------------------------------------------------------------------------
# Untested skills pass through unchanged
# ---------------------------------------------------------------------------

class TestUntestedSkill:
    def test_untested_skill_registered_without_modification(self, tmp_path):
        extra = "provider_support:\n  claude-code: untested\n"
        skill_path = _write_skill(tmp_path / "src", "untested-skill", "Untested desc", extra)
        original = skill_path.read_text()
        skill = load_skill(skill_path)

        target = tmp_path / "plugin"
        results = ClaudeCodeAdapter().register([skill], target)

        r = results[0]
        assert r.registered is True
        registered = (target / "skills" / "untested-skill" / "SKILL.md").read_text()
        assert registered == original


# ---------------------------------------------------------------------------
# unregister
# ---------------------------------------------------------------------------

class TestUnregister:
    def test_unregister_removes_skill_dir(self, tmp_path):
        skill_path = _write_skill(tmp_path / "src", "to-remove", "Removable")
        skill = load_skill(skill_path)
        target = tmp_path / "plugin"
        adapter = ClaudeCodeAdapter()
        adapter.register([skill], target)
        assert (target / "skills" / "to-remove").exists()

        adapter.unregister(["to-remove"], target)
        assert not (target / "skills" / "to-remove").exists()

    def test_unregister_nonexistent_is_safe(self, tmp_path):
        adapter = ClaudeCodeAdapter()
        adapter.unregister(["ghost-skill"], tmp_path / "plugin")  # no error


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    def test_claude_code_adapter_satisfies_skill_adapter_protocol(self):
        from otaman_adapters.adapter import SkillAdapter
        assert isinstance(ClaudeCodeAdapter(), SkillAdapter)


# ---------------------------------------------------------------------------
# Spike: real skill samples from otaman-plugin
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not CTO_ADVISOR_PATH.exists(),
    reason="otaman-plugin not present on disk",
)
class TestRealSkillSamples:
    """Verify the 3 spike samples load and register correctly."""

    SAMPLES = [
        ("cto-advisor", CTO_ADVISOR_PATH),
        ("knowledge-capture", KNOWLEDGE_CAPTURE_PATH),
        ("project-estimator", PROJECT_ESTIMATOR_PATH),
    ]

    def test_all_three_skills_load_without_error(self):
        for name, path in self.SAMPLES:
            skill = load_skill(path)
            assert skill.name == name, f"{name}: name mismatch"
            assert len(skill.description) > 20, f"{name}: description too short"

    def test_all_three_default_to_full_for_claude_code(self):
        for name, path in self.SAMPLES:
            skill = load_skill(path)
            assert skill.compatibility_for("claude-code") == CompatibilityLevel.FULL, (
                f"{name}: expected full compat (no provider_support declared)"
            )

    def test_all_three_register_successfully(self, tmp_path):
        skills = [load_skill(path) for _, path in self.SAMPLES]
        target = tmp_path / "plugin"
        results = ClaudeCodeAdapter().register(skills, target)

        for r in results:
            assert r.registered, f"{r.skill_name}: registration failed — {r.reason}"
            assert r.target_path is not None
            assert r.target_path.exists()

    def test_registered_skills_have_valid_frontmatter(self, tmp_path):
        skills = [load_skill(path) for _, path in self.SAMPLES]
        target = tmp_path / "plugin"
        ClaudeCodeAdapter().register(skills, target)

        for name, _ in self.SAMPLES:
            registered_path = target / "skills" / name / "SKILL.md"
            content = registered_path.read_text()
            parts = content.split("---", 2)
            assert len(parts) >= 3, f"{name}: registered file has no frontmatter"
            fm = yaml.safe_load(parts[1])
            assert fm["name"] == name
            assert "description" in fm

    def test_skill_bodies_preserved_after_registration(self, tmp_path):
        skills = [load_skill(path) for _, path in self.SAMPLES]
        target = tmp_path / "plugin"
        ClaudeCodeAdapter().register(skills, target)

        for name, source_path in self.SAMPLES:
            original_body = source_path.read_text().split("---", 2)[-1]
            registered_body = (
                (target / "skills" / name / "SKILL.md").read_text().split("---", 2)[-1]
            )
            assert original_body == registered_body, f"{name}: body was mutated"

    def test_cto_advisor_references_dir_copied(self, tmp_path):
        skill = load_skill(CTO_ADVISOR_PATH)
        target = tmp_path / "plugin"
        ClaudeCodeAdapter().register([skill], target)

        refs = target / "skills" / "cto-advisor" / "references"
        assert refs.exists(), "cto-advisor references/ dir not copied"

    def test_project_estimator_references_dir_copied(self, tmp_path):
        skill = load_skill(PROJECT_ESTIMATOR_PATH)
        target = tmp_path / "plugin"
        ClaudeCodeAdapter().register([skill], target)

        refs = target / "skills" / "project-estimator" / "references"
        assert refs.exists(), "project-estimator references/ dir not copied"
