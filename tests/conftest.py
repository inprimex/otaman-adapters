"""Shared fixtures for otaman-adapters tests."""

from pathlib import Path

import pytest

# Paths to the real Otaman skill files used as spike samples.
_PLUGIN_SKILLS = Path(__file__).parent.parent.parent / "otaman-plugin" / "skills"

CTO_ADVISOR_PATH = _PLUGIN_SKILLS / "cto-advisor" / "SKILL.md"
KNOWLEDGE_CAPTURE_PATH = _PLUGIN_SKILLS / "knowledge-capture" / "SKILL.md"
PROJECT_ESTIMATOR_PATH = _PLUGIN_SKILLS / "project-estimator" / "SKILL.md"


def pytest_configure(config):
    """Skip real-skill tests gracefully when the plugin repo is absent."""
    pass


@pytest.fixture
def real_skills_available() -> bool:
    return CTO_ADVISOR_PATH.exists()
