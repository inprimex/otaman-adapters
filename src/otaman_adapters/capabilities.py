"""Adapter capability declarations for the Otaman routing contract.

This module defines ``DataClassification`` and ``AdapterCapabilities`` — the
types that adapters use to declare which data sensitivity tiers their default
backend is certified to handle.

**Source of truth**: ``otaman_core.routing`` (owned by core-agent, per ADR-003).
This local copy exists because ``otaman-core`` has not yet published
``routing.py`` (core-agent task 1.4, ``otaman-router-v1-design`` change).

**Migration path**: once ``otaman_core.routing`` is published, replace the
definitions here with::

    from otaman_core.routing import DataClassification, AdapterCapabilities

and update the adapters' imports accordingly.  The dataclass field names and
enum values are intentionally identical to the core definitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class DataClassification(str, Enum):
    """Ordered sensitivity tiers for data handled in a task.

    Mirrors ``otaman_core.routing.DataClassification`` (research doc:
    ``otaman-router-v1-design/research/data-classification-levels.md``).

    INTERNAL   — non-public data with no regulatory label; suitable for any
                 backend the operator has vetted.
    SENSITIVE  — commercially sensitive / contractually restricted data; no
                 specific regulation, but confidentiality obligations exist.
    PII        — Personally Identifiable Information (GDPR/CCPA); requires a
                 signed Data Processing Agreement (DPA) with the backend.
    PHI        — Protected Health Information (HIPAA); requires a signed BAA.
    REGULATED  — Catch-all for non-PHI regulated data: PCI-DSS, ITAR/EAR,
                 EU sovereign requirements, government-classified content.
                 Typically requires on-premises or sovereignty-certified cloud.
    """

    INTERNAL  = "internal"
    SENSITIVE = "sensitive"
    PII       = "pii"
    PHI       = "phi"
    REGULATED = "regulated"


@dataclass(frozen=True)
class AdapterCapabilities:
    """Declares what an adapter's default backend is certified to handle.

    ``compliance`` lists the ``DataClassification`` tiers the adapter's
    *default* backend configuration is cleared for.  Higher tiers (PHI,
    REGULATED) require the operator to configure a backend with appropriate
    certifications (BAA, sovereignty cert, on-prem vLLM).

    The router's compliance rule (rule 1) performs a membership check:
    ``task_classification in adapter.capabilities.compliance``.

    Attributes:
        compliance: Ordered list of DataClassification values this adapter's
            default backend handles.  May be overridden at deployment time
            via ``routing.yaml`` per-backend configuration.
        notes: Optional human-readable explanation of compliance posture,
            useful for operator documentation and audit trails.
    """

    compliance: tuple[DataClassification, ...] = field(default_factory=tuple)
    notes: str = ""

    @classmethod
    def for_levels(
        cls,
        *levels: DataClassification,
        notes: str = "",
    ) -> "AdapterCapabilities":
        """Convenience constructor — pass levels as positional args."""
        return cls(compliance=tuple(levels), notes=notes)

    def clears(self, classification: DataClassification) -> bool:
        """Return True if this adapter is cleared for the given classification."""
        return classification in self.compliance
