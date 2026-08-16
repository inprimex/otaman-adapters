"""Tests for OpenAIAgentsAdapter — task 1.5 spike.

Mirrors the structure of test_claude_code_adapter.py for cross-adapter
consistency, with OpenAI-specific assertions about the instructions block.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from conftest import (
    CTO_ADVISOR_PATH,
    KNOWLEDGE_CAPTURE_PATH,
    PROJECT_ESTIMATOR_PATH,
)

from otaman_adapters import (
    CompatibilityLevel,
    OpenAIAgentsAdapter,
    Skill,
    load_skill,
)
from otaman_adapters.adapter import SkillAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(
    name: str,
    description: str,
    *,
    compat: dict[str, str] | None = None,
    notes: dict[str, str] | None = None,
    triggers: list[str] | None = None,
    source_path: Path | None = None,
    tmp_path: Path | None = None,
) -> Skill:
    """Build a minimal Skill for use in tests without touching the filesystem."""
    if source_path is None:
        assert tmp_path is not None, "provide either source_path or tmp_path"
        source_path = tmp_path / f"{name}.md"
        frontmatter: dict[str, Any] = {"name": name, "description": description}
        if compat:
            frontmatter["provider_support"] = compat
        if notes:
            frontmatter["provider_notes"] = notes
        if triggers:
            frontmatter["triggers"] = triggers
        source_path.write_text(
            "---\n" + yaml.dump(frontmatter) + "---\n\nbody\n",
            encoding="utf-8",
        )
        return load_skill(source_path)
    return load_skill(source_path)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> OpenAIAgentsAdapter:
    return OpenAIAgentsAdapter()


@pytest.fixture
def full_skill(tmp_path) -> Skill:
    return _make_skill("my-skill", "A useful skill.", tmp_path=tmp_path)


@pytest.fixture
def partial_skill(tmp_path) -> Skill:
    return _make_skill(
        "partial-skill",
        "A partial skill.",
        compat={"openai-agents": "partial"},
        notes={"openai-agents": "file tools unavailable"},
        tmp_path=tmp_path,
    )


@pytest.fixture
def unsupported_skill(tmp_path) -> Skill:
    return _make_skill(
        "unsupported-skill",
        "A skill that cannot run here.",
        compat={"openai-agents": "unsupported"},
        tmp_path=tmp_path,
    )


@pytest.fixture
def skill_with_triggers(tmp_path) -> Skill:
    return _make_skill(
        "triggered-skill",
        "A skill with trigger cues.",
        triggers=["estimate this", "how long would X take"],
        tmp_path=tmp_path,
    )


# ---------------------------------------------------------------------------
# TestOutputFiles
# ---------------------------------------------------------------------------


class TestOutputFiles:
    """Adapter writes skills_block.md and skills_block.py to target_dir."""

    def test_skills_block_md_created(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        assert (tmp_path / "skills_block.md").exists()

    def test_skills_block_py_created(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        assert (tmp_path / "skills_block.py").exists()

    def test_target_dir_created_if_absent(self, adapter, full_skill, tmp_path):
        target = tmp_path / "deep" / "nested" / "dir"
        adapter.register([full_skill], target)
        assert (target / "skills_block.md").exists()

    def test_empty_skill_list_produces_empty_files(self, adapter, tmp_path):
        adapter.register([], tmp_path)
        assert (tmp_path / "skills_block.md").read_text() == ""

    def test_py_file_contains_skill_instructions_constant(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        py_src = (tmp_path / "skills_block.py").read_text()
        assert "SKILL_INSTRUCTIONS" in py_src

    def test_py_file_contains_registered_skills_constant(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        py_src = (tmp_path / "skills_block.py").read_text()
        assert "REGISTERED_SKILLS" in py_src
        assert "my-skill" in py_src

    def test_py_file_is_syntactically_valid(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        py_src = (tmp_path / "skills_block.py").read_text()
        # compile() raises SyntaxError if the source is invalid
        compile(py_src, "skills_block.py", "exec")


# ---------------------------------------------------------------------------
# TestInstructionsContent
# ---------------------------------------------------------------------------


class TestInstructionsContent:
    """The generated instructions block contains the correct skill descriptions."""

    def test_full_skill_description_in_instructions(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "A useful skill." in md

    def test_skill_name_in_instructions(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "my-skill" in md

    def test_multiple_skills_all_appear(self, adapter, full_skill, partial_skill, tmp_path):
        adapter.register([full_skill, partial_skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "my-skill" in md
        assert "partial-skill" in md

    def test_instructions_has_header(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "## Active Skills" in md

    def test_skill_with_triggers_lists_them(self, adapter, skill_with_triggers, tmp_path):
        adapter.register([skill_with_triggers], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "estimate this" in md
        assert "how long would X take" in md

    def test_skill_without_triggers_no_trigger_section(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "Trigger cues" not in md


# ---------------------------------------------------------------------------
# TestUnsupportedSkill
# ---------------------------------------------------------------------------


class TestUnsupportedSkill:
    def test_unsupported_skill_not_registered(self, adapter, unsupported_skill, tmp_path):
        results = adapter.register([unsupported_skill], tmp_path)
        assert len(results) == 1
        assert results[0].registered is False

    def test_unsupported_skill_absent_from_instructions(self, adapter, unsupported_skill, tmp_path):
        adapter.register([unsupported_skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "unsupported-skill" not in md

    def test_mixed_set_excludes_only_unsupported(
        self, adapter, full_skill, unsupported_skill, tmp_path
    ):
        results = adapter.register([full_skill, unsupported_skill], tmp_path)
        registered = [r for r in results if r.registered]
        skipped = [r for r in results if not r.registered]
        assert len(registered) == 1
        assert registered[0].skill_name == "my-skill"
        assert len(skipped) == 1
        assert skipped[0].skill_name == "unsupported-skill"


# ---------------------------------------------------------------------------
# TestPartialCaveat
# ---------------------------------------------------------------------------


class TestPartialCaveat:
    def test_partial_skill_is_registered(self, adapter, partial_skill, tmp_path):
        results = adapter.register([partial_skill], tmp_path)
        assert results[0].registered is True

    def test_caveat_injected_into_instructions(self, adapter, partial_skill, tmp_path):
        adapter.register([partial_skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "CAVEAT" in md
        assert "file tools unavailable" in md

    def test_caveat_result_populated(self, adapter, partial_skill, tmp_path):
        results = adapter.register([partial_skill], tmp_path)
        assert results[0].caveat == "file tools unavailable"

    def test_partial_description_still_present(self, adapter, partial_skill, tmp_path):
        adapter.register([partial_skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "A partial skill." in md


# ---------------------------------------------------------------------------
# TestUntestedSkill
# ---------------------------------------------------------------------------


class TestUntestedSkill:
    def test_untested_skill_registered_without_caveat(self, adapter, tmp_path):
        skill = _make_skill(
            "untested-skill",
            "Desc.",
            compat={"openai-agents": "untested"},
            tmp_path=tmp_path,
        )
        results = adapter.register([skill], tmp_path)
        assert results[0].registered is True
        assert results[0].caveat is None

    def test_untested_description_unchanged(self, adapter, tmp_path):
        skill = _make_skill(
            "untested-skill",
            "Original desc.",
            compat={"openai-agents": "untested"},
            tmp_path=tmp_path,
        )
        adapter.register([skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "Original desc." in md
        assert "CAVEAT" not in md


# ---------------------------------------------------------------------------
# TestReturnValues
# ---------------------------------------------------------------------------


class TestReturnValues:
    def test_returns_one_result_per_skill(self, adapter, full_skill, partial_skill, tmp_path):
        results = adapter.register([full_skill, partial_skill], tmp_path)
        assert len(results) == 2

    def test_full_result_has_correct_target_path(self, adapter, full_skill, tmp_path):
        results = adapter.register([full_skill], tmp_path)
        assert results[0].target_path == tmp_path / "skills_block.md"

    def test_unsupported_result_has_no_target_path(self, adapter, unsupported_skill, tmp_path):
        results = adapter.register([unsupported_skill], tmp_path)
        assert results[0].target_path is None

    def test_result_skill_names_match(self, adapter, full_skill, unsupported_skill, tmp_path):
        results = adapter.register([full_skill, unsupported_skill], tmp_path)
        names = {r.skill_name for r in results}
        assert names == {"my-skill", "unsupported-skill"}


# ---------------------------------------------------------------------------
# TestUnregister
# ---------------------------------------------------------------------------


class TestUnregister:
    def test_unregister_removes_output_files(self, adapter, full_skill, tmp_path):
        adapter.register([full_skill], tmp_path)
        assert (tmp_path / "skills_block.md").exists()
        adapter.unregister(["my-skill"], tmp_path)
        assert not (tmp_path / "skills_block.md").exists()
        assert not (tmp_path / "skills_block.py").exists()

    def test_unregister_missing_files_is_safe(self, adapter, tmp_path):
        # Should not raise even when files don't exist
        adapter.unregister(["nonexistent"], tmp_path)


# ---------------------------------------------------------------------------
# TestBuildInstructionsMethod
# ---------------------------------------------------------------------------


class TestBuildInstructionsMethod:
    """build_instructions() returns the string without writing files."""

    def test_returns_string(self, adapter, full_skill):
        result = adapter.build_instructions([full_skill])
        assert isinstance(result, str)

    def test_contains_skill_description(self, adapter, full_skill):
        result = adapter.build_instructions([full_skill])
        assert "A useful skill." in result

    def test_empty_list_returns_empty_string(self, adapter):
        result = adapter.build_instructions([])
        assert result == ""

    def test_no_files_written(self, adapter, full_skill, tmp_path):
        # build_instructions must NOT touch the filesystem
        adapter.build_instructions([full_skill])
        assert not (tmp_path / "skills_block.md").exists()

    def test_unsupported_excluded(self, adapter, unsupported_skill):
        result = adapter.build_instructions([unsupported_skill])
        assert "unsupported-skill" not in result


# ---------------------------------------------------------------------------
# TestProtocolConformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_openai_agents_adapter_satisfies_skill_adapter_protocol(self, adapter):
        assert isinstance(adapter, SkillAdapter)

    def test_runtime_id(self, adapter):
        assert adapter.runtime_id == "openai-agents"


# ---------------------------------------------------------------------------
# TestRealSkillSamples
# ---------------------------------------------------------------------------


class TestRealSkillSamples:
    """Integration tests using the actual skill files from otaman-plugin."""

    @pytest.fixture(autouse=True)
    def skip_if_absent(self, real_skills_available):
        if not real_skills_available:
            pytest.skip("otaman-plugin skills not present")

    def test_all_three_skills_load_without_error(self):
        for path in (CTO_ADVISOR_PATH, KNOWLEDGE_CAPTURE_PATH, PROJECT_ESTIMATOR_PATH):
            load_skill(path)

    def test_all_three_default_to_full_for_openai_agents(self):
        for path in (CTO_ADVISOR_PATH, KNOWLEDGE_CAPTURE_PATH, PROJECT_ESTIMATOR_PATH):
            skill = load_skill(path)
            assert skill.compatibility_for("openai-agents") == CompatibilityLevel.FULL

    def test_all_three_register_successfully(self, tmp_path):
        skills = [
            load_skill(CTO_ADVISOR_PATH),
            load_skill(KNOWLEDGE_CAPTURE_PATH),
            load_skill(PROJECT_ESTIMATOR_PATH),
        ]
        results = OpenAIAgentsAdapter().register(skills, tmp_path)
        assert all(r.registered for r in results), [r for r in results if not r.registered]

    def test_instructions_contain_all_skill_names(self, tmp_path):
        skills = [
            load_skill(CTO_ADVISOR_PATH),
            load_skill(KNOWLEDGE_CAPTURE_PATH),
            load_skill(PROJECT_ESTIMATOR_PATH),
        ]
        OpenAIAgentsAdapter().register(skills, tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        assert "cto-advisor" in md
        assert "knowledge-capture" in md
        assert "project-estimator" in md

    def test_instructions_contain_all_descriptions(self, tmp_path):
        skills = [
            load_skill(CTO_ADVISOR_PATH),
            load_skill(KNOWLEDGE_CAPTURE_PATH),
            load_skill(PROJECT_ESTIMATOR_PATH),
        ]
        OpenAIAgentsAdapter().register(skills, tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        for skill in skills:
            assert skill.description[:40] in md

    def test_py_file_is_executable(self, tmp_path):
        skills = [load_skill(CTO_ADVISOR_PATH)]
        OpenAIAgentsAdapter().register(skills, tmp_path)
        py_src = (tmp_path / "skills_block.py").read_text()
        ns: dict = {}
        exec(compile(py_src, "skills_block.py", "exec"), ns)
        assert isinstance(ns["SKILL_INSTRUCTIONS"], str)
        assert isinstance(ns["REGISTERED_SKILLS"], list)
        assert "cto-advisor" in ns["REGISTERED_SKILLS"]

    def test_knowledge_capture_triggers_in_instructions(self, tmp_path):
        """knowledge-capture has triggers in its frontmatter — verify they appear."""
        skill = load_skill(KNOWLEDGE_CAPTURE_PATH)
        if not skill.raw_frontmatter.get("triggers"):
            pytest.skip("knowledge-capture has no triggers field in frontmatter")
        OpenAIAgentsAdapter().register([skill], tmp_path)
        md = (tmp_path / "skills_block.md").read_text()
        # At least one trigger should appear in the instructions
        first_trigger = skill.raw_frontmatter["triggers"][0]
        assert first_trigger in md

    def test_build_instructions_matches_register_output(self, tmp_path):
        """build_instructions() and register() must produce identical skill text."""
        skills = [
            load_skill(CTO_ADVISOR_PATH),
            load_skill(KNOWLEDGE_CAPTURE_PATH),
            load_skill(PROJECT_ESTIMATOR_PATH),
        ]
        adapter = OpenAIAgentsAdapter()
        direct = adapter.build_instructions(skills)
        adapter.register(skills, tmp_path)
        from_file = (tmp_path / "skills_block.md").read_text()
        assert direct == from_file
