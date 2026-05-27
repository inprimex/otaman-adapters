"""Tests for AdapterCapabilities + compliance declarations — task 4.1 / 4.2.

Covers:
- DataClassification enum values + behaviour
- AdapterCapabilities construction + clears() method
- Compliance declarations on each adapter
- Backward compatibility: adding .capabilities does not break existing tests
"""
from __future__ import annotations

import pytest

from otaman_adapters import (
    AdapterCapabilities,
    DataClassification,
    ClaudeCodeAdapter,
    OpenAIAgentsAdapter,
    GeminiCliAdapter,
    GeminiApiAdapter,
)


# ---------------------------------------------------------------------------
# DataClassification
# ---------------------------------------------------------------------------

class TestDataClassification:
    def test_all_five_values_present(self):
        values = {dc.value for dc in DataClassification}
        assert values == {"internal", "sensitive", "pii", "phi", "regulated"}

    def test_string_enum_values(self):
        assert DataClassification.INTERNAL == "internal"
        assert DataClassification.SENSITIVE == "sensitive"
        assert DataClassification.PII == "pii"
        assert DataClassification.PHI == "phi"
        assert DataClassification.REGULATED == "regulated"

    def test_usable_as_set_member(self):
        s = {DataClassification.INTERNAL, DataClassification.SENSITIVE}
        assert DataClassification.INTERNAL in s
        assert DataClassification.PHI not in s


# ---------------------------------------------------------------------------
# AdapterCapabilities
# ---------------------------------------------------------------------------

class TestAdapterCapabilities:
    def test_for_levels_convenience_constructor(self):
        caps = AdapterCapabilities.for_levels(
            DataClassification.INTERNAL,
            DataClassification.SENSITIVE,
        )
        assert DataClassification.INTERNAL in caps.compliance
        assert DataClassification.SENSITIVE in caps.compliance
        assert DataClassification.PHI not in caps.compliance

    def test_clears_returns_true_for_declared_level(self):
        caps = AdapterCapabilities.for_levels(DataClassification.INTERNAL)
        assert caps.clears(DataClassification.INTERNAL) is True

    def test_clears_returns_false_for_undeclared_level(self):
        caps = AdapterCapabilities.for_levels(DataClassification.INTERNAL)
        assert caps.clears(DataClassification.PHI) is False

    def test_empty_compliance_clears_nothing(self):
        caps = AdapterCapabilities()
        for dc in DataClassification:
            assert caps.clears(dc) is False

    def test_notes_field(self):
        caps = AdapterCapabilities.for_levels(
            DataClassification.INTERNAL,
            notes="test note",
        )
        assert caps.notes == "test note"

    def test_frozen_immutable(self):
        caps = AdapterCapabilities.for_levels(DataClassification.INTERNAL)
        with pytest.raises((AttributeError, TypeError)):
            caps.notes = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ClaudeCodeAdapter compliance
# ---------------------------------------------------------------------------

class TestClaudeCodeAdapterCompliance:
    def test_has_capabilities_attribute(self):
        assert hasattr(ClaudeCodeAdapter, "capabilities")

    def test_capabilities_is_adapter_capabilities_instance(self):
        assert isinstance(ClaudeCodeAdapter.capabilities, AdapterCapabilities)

    def test_clears_internal(self):
        assert ClaudeCodeAdapter.capabilities.clears(DataClassification.INTERNAL)

    def test_clears_sensitive(self):
        assert ClaudeCodeAdapter.capabilities.clears(DataClassification.SENSITIVE)

    def test_does_not_clear_phi_by_default(self):
        # Anthropic standard API: no BAA → PHI not cleared by default
        assert not ClaudeCodeAdapter.capabilities.clears(DataClassification.PHI)

    def test_does_not_clear_regulated_by_default(self):
        assert not ClaudeCodeAdapter.capabilities.clears(DataClassification.REGULATED)

    def test_does_not_clear_pii_by_default(self):
        assert not ClaudeCodeAdapter.capabilities.clears(DataClassification.PII)

    def test_capabilities_accessible_on_instance(self):
        adapter = ClaudeCodeAdapter()
        assert adapter.capabilities is ClaudeCodeAdapter.capabilities

    def test_notes_mention_baa(self):
        assert "BAA" in ClaudeCodeAdapter.capabilities.notes


# ---------------------------------------------------------------------------
# OpenAIAgentsAdapter compliance
# ---------------------------------------------------------------------------

class TestOpenAIAgentsAdapterCompliance:
    def test_has_capabilities_attribute(self):
        assert hasattr(OpenAIAgentsAdapter, "capabilities")

    def test_capabilities_is_adapter_capabilities_instance(self):
        assert isinstance(OpenAIAgentsAdapter.capabilities, AdapterCapabilities)

    def test_clears_internal(self):
        assert OpenAIAgentsAdapter.capabilities.clears(DataClassification.INTERNAL)

    def test_clears_sensitive(self):
        assert OpenAIAgentsAdapter.capabilities.clears(DataClassification.SENSITIVE)

    def test_clears_phi(self):
        # Azure OpenAI with BAA covers PHI — declared as configurable default
        assert OpenAIAgentsAdapter.capabilities.clears(DataClassification.PHI)

    def test_clears_regulated(self):
        # Azure OpenAI with appropriate cert covers REGULATED
        assert OpenAIAgentsAdapter.capabilities.clears(DataClassification.REGULATED)

    def test_notes_mention_azure(self):
        assert "Azure" in OpenAIAgentsAdapter.capabilities.notes

    def test_notes_mention_baa(self):
        assert "BAA" in OpenAIAgentsAdapter.capabilities.notes

    def test_capabilities_accessible_on_instance(self):
        adapter = OpenAIAgentsAdapter()
        assert adapter.capabilities is OpenAIAgentsAdapter.capabilities


# ---------------------------------------------------------------------------
# GeminiCliAdapter compliance
# ---------------------------------------------------------------------------

class TestGeminiCliAdapterCompliance:
    def test_has_capabilities_attribute(self):
        assert hasattr(GeminiCliAdapter, "capabilities")

    def test_clears_internal(self):
        assert GeminiCliAdapter.capabilities.clears(DataClassification.INTERNAL)

    def test_clears_sensitive(self):
        assert GeminiCliAdapter.capabilities.clears(DataClassification.SENSITIVE)

    def test_does_not_clear_phi_by_default(self):
        assert not GeminiCliAdapter.capabilities.clears(DataClassification.PHI)

    def test_does_not_clear_regulated_by_default(self):
        assert not GeminiCliAdapter.capabilities.clears(DataClassification.REGULATED)


# ---------------------------------------------------------------------------
# GeminiApiAdapter compliance
# ---------------------------------------------------------------------------

class TestGeminiApiAdapterCompliance:
    def test_has_capabilities_attribute(self):
        assert hasattr(GeminiApiAdapter, "capabilities")

    def test_clears_internal(self):
        assert GeminiApiAdapter.capabilities.clears(DataClassification.INTERNAL)

    def test_clears_sensitive(self):
        assert GeminiApiAdapter.capabilities.clears(DataClassification.SENSITIVE)

    def test_does_not_clear_phi_by_default(self):
        assert not GeminiApiAdapter.capabilities.clears(DataClassification.PHI)


# ---------------------------------------------------------------------------
# Task 4.2 — backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Adding .capabilities must not break any existing adapter behaviour."""

    def test_claude_code_register_still_works(self, tmp_path):
        """ClaudeCodeAdapter.register() is unaffected by the new capabilities attr."""
        from otaman_adapters import Skill, CompatibilityLevel
        from pathlib import Path
        import yaml

        src = tmp_path / "my-skill" / "SKILL.md"
        src.parent.mkdir()
        src.write_text("---\nname: my-skill\ndescription: A skill.\n---\nbody\n")

        from otaman_adapters import load_skill
        skill = load_skill(src)
        results = ClaudeCodeAdapter().register([skill], tmp_path / "out")
        assert results[0].registered is True

    def test_openai_agents_register_still_works(self, tmp_path):
        src = tmp_path / "my-skill.md"
        src.write_text("---\nname: my-skill\ndescription: A skill.\n---\nbody\n")

        from otaman_adapters import load_skill
        skill = load_skill(src)
        results = OpenAIAgentsAdapter().register([skill], tmp_path / "out")
        assert results[0].registered is True

    def test_capabilities_is_class_level_not_instance_level(self):
        """capabilities is declared on the class, not created per-instance."""
        a1 = ClaudeCodeAdapter()
        a2 = ClaudeCodeAdapter()
        assert a1.capabilities is a2.capabilities
        assert a1.capabilities is ClaudeCodeAdapter.capabilities

    def test_existing_protocol_still_satisfied(self):
        from otaman_adapters import SkillAdapter
        assert isinstance(ClaudeCodeAdapter(), SkillAdapter)
        assert isinstance(OpenAIAgentsAdapter(), SkillAdapter)
