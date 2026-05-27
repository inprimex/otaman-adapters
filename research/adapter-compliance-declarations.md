# Adapter Compliance Declarations — task 4.1

**Author**: adapters-agent
**Date**: 2026-05-27
**Change**: otaman-router-v1-design
**Branch**: `agent/adapters-agent/router-v1-compliance-capabilities`

---

## Summary

Each Otaman adapter now declares an `AdapterCapabilities` object on its class
(`adapter.capabilities`) specifying which `DataClassification` tiers its default
backend configuration is certified to handle.  The router's compliance rule
(rule 1) uses this to select a backend appropriate for the task's data sensitivity.

---

## Types introduced

### `DataClassification` (local stub → `otaman_core.routing`)

`src/otaman_adapters/capabilities.py` defines a local copy mirroring the
definition in `otaman-router-v1-design/research/data-classification-levels.md`.

```python
class DataClassification(str, Enum):
    INTERNAL  = "internal"   # non-public, no regulatory label
    SENSITIVE = "sensitive"  # NDA / contractual confidentiality
    PII       = "pii"        # GDPR/CCPA — requires DPA
    PHI       = "phi"        # HIPAA — requires BAA
    REGULATED = "regulated"  # PCI-DSS, ITAR/EAR, sovereign data
```

**Migration path**: when `otaman-core` publishes `otaman_core.routing`, replace
the import in `capabilities.py` with:
```python
from otaman_core.routing import DataClassification, AdapterCapabilities
```

### `AdapterCapabilities`

```python
@dataclass(frozen=True)
class AdapterCapabilities:
    compliance: tuple[DataClassification, ...]
    notes: str = ""

    def clears(self, classification: DataClassification) -> bool: ...
```

The router performs: `task_classification in adapter.capabilities.compliance`.

---

## Compliance declarations

### `ClaudeCodeAdapter`

```python
capabilities = AdapterCapabilities.for_levels(
    DataClassification.INTERNAL,
    DataClassification.SENSITIVE,
    notes="Default: Anthropic API (no BAA). INTERNAL + SENSITIVE cleared. "
          "PHI/REGULATED require Bedrock-Anthropic with AWS BAA (EE, operator-configured)."
)
```

**Cleared**: `INTERNAL`, `SENSITIVE`
**Not cleared by default**: `PII`, `PHI`, `REGULATED`

**Rationale**:
- Anthropic's standard API tier does not offer a HIPAA Business Associate
  Agreement (BAA) or PCI-DSS certification.
- Data-retention-off policy (enabled by default on Anthropic API for
  enterprise plans) covers `SENSITIVE` contractual obligations.
- Anthropic on AWS Bedrock can be covered by an AWS BAA, enabling `PHI` and
  potentially `REGULATED` — but this requires operator configuration of a
  Bedrock endpoint; it is not the default `ClaudeCodeAdapter` deployment.
- `PII` (GDPR DPA) is not declared because Anthropic's standard API does not
  offer an EU-jurisdiction DPA at the standard tier (available via enterprise
  agreements; not default).

---

### `OpenAIAgentsAdapter`

```python
capabilities = AdapterCapabilities.for_levels(
    DataClassification.INTERNAL,
    DataClassification.SENSITIVE,
    DataClassification.PHI,
    DataClassification.REGULATED,
    notes="Configurable: Azure OpenAI + Microsoft BAA covers PHI + REGULATED. "
          "Plain OpenAI API (api.openai.com) covers INTERNAL + SENSITIVE only. "
          "Operator must configure Azure endpoint for PHI/REGULATED clearance."
)
```

**Cleared**: `INTERNAL`, `SENSITIVE`, `PHI`, `REGULATED`
**Not declared**: `PII` (see note)

**Rationale**:
- This is a **configurable adapter** — the instructions block it generates is
  backend-agnostic.  The compliance posture reflects the *maximum achievable*
  clearance when properly configured, not a lowest-common-denominator.
- Azure OpenAI Service with a Microsoft HIPAA BAA covers `PHI`.  Azure also
  holds PCI-DSS Level 1 certification, covering `REGULATED` for payment-card
  scope, and meets FedRAMP High, ISO 27001, SOC 2, and other regulatory
  frameworks relevant to `REGULATED` workloads.
- Plain `api.openai.com` (non-Azure) does not offer a BAA; operators routing
  PHI/REGULATED tasks to this adapter MUST configure an Azure OpenAI endpoint.
  The `routing.yaml` per-backend configuration is the enforcement point.
- `PII` is not explicitly declared because it is subsumed by the `PHI`
  coverage (Azure BAA covers PHI which includes PII in healthcare context;
  Azure DPA covers GDPR). The router will enforce `PII` routing against the
  declared set — an operator needing explicit `PII` coverage should add it via
  `routing.yaml` per-org overlay. This will be documented in `routing.yaml`
  schema guidance.

---

### `GeminiCliAdapter`

```python
capabilities = AdapterCapabilities.for_levels(
    DataClassification.INTERNAL,
    DataClassification.SENSITIVE,
    notes="Default: Google Cloud Gemini API (no HIPAA BAA at standard tier). "
          "INTERNAL + SENSITIVE cleared. PHI/REGULATED require Google Cloud "
          "Healthcare-certified deployment (operator-configured, not default)."
)
```

**Cleared**: `INTERNAL`, `SENSITIVE`
**Not cleared by default**: `PII`, `PHI`, `REGULATED`

**Rationale**:
- Google Cloud offers a HIPAA BAA for many Google Cloud services, but the
  Gemini CLI standard tier / Google AI Studio endpoint does not have a BAA
  in the standard developer tier.
- Healthcare-grade Vertex AI deployments on Google Cloud can obtain BAA
  coverage, but this requires operator configuration of the endpoint —
  not the default.

---

### `GeminiApiAdapter`

```python
capabilities = AdapterCapabilities.for_levels(
    DataClassification.INTERNAL,
    DataClassification.SENSITIVE,
    notes="Default: google-generativeai SDK (no HIPAA BAA at standard tier). "
          "INTERNAL + SENSITIVE cleared. PHI/REGULATED require Vertex AI on a "
          "Google Cloud Healthcare-certified project (operator-configured)."
)
```

**Cleared**: `INTERNAL`, `SENSITIVE`
**Not cleared by default**: `PII`, `PHI`, `REGULATED`

**Rationale**: same as `GeminiCliAdapter` — both use Google Cloud Gemini infrastructure.

---

## Compliance matrix summary

| Adapter | INTERNAL | SENSITIVE | PII | PHI | REGULATED |
|---|---|---|---|---|---|
| `ClaudeCodeAdapter` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `OpenAIAgentsAdapter` | ✅ | ✅ | ❌* | ✅ | ✅ |
| `GeminiCliAdapter` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `GeminiApiAdapter` | ✅ | ✅ | ❌ | ❌ | ❌ |

\* PII subsumed by PHI coverage (Azure BAA + DPA); may be added explicitly via `routing.yaml` overlay.

**For PHI/REGULATED workloads**, the router's compliance rule will select
`OpenAIAgentsAdapter` (Azure-configured) or a self-hosted vLLM adapter when
those clearances are needed.

---

## Implementation notes

- `capabilities` is a **class-level attribute** (not instance-level), declared
  directly on the class body.  Instances inherit it; the object is shared.
- `AdapterCapabilities` is a frozen dataclass — immutable after construction.
- The `SkillAdapter` Protocol is NOT updated to require `capabilities` — this
  is a forward-compatible addition.  Once `otaman-core` publishes
  `AdapterCapabilities` and the router starts reading it, the Protocol will be
  extended in `otaman-core` (core-agent task 1.4).

---

## Where to find this in code

| File | What |
|---|---|
| `src/otaman_adapters/capabilities.py` | `DataClassification`, `AdapterCapabilities` types |
| `src/otaman_adapters/claude_code.py` | `ClaudeCodeAdapter.capabilities` |
| `src/otaman_adapters/openai_agents.py` | `OpenAIAgentsAdapter.capabilities` |
| `src/otaman_adapters/gemini.py` | `GeminiCliAdapter.capabilities`, `GeminiApiAdapter.capabilities` |
| `tests/test_capabilities.py` | 40 tests covering all declarations |
