# Adapter Compliance Declarations

Each Otaman adapter declares an `AdapterCapabilities` object describing which
data-classification tiers its *default* backend configuration is certified to
handle. This document explains those declarations and their rationale.

---

## Summary

Each Otaman adapter now declares an `AdapterCapabilities` object on its class
(`adapter.capabilities`) specifying which `DataClassification` tiers its default
backend configuration is certified to handle.  The router's compliance rule
(rule 1) uses this to select a backend appropriate for the task's data sensitivity.

---

## Types introduced

### `DataClassification` (local stub → `otaman_core.routing`)

`src/otaman_adapters/capabilities.py` defines a local copy that mirrors the
canonical data-classification levels used by the platform's routing layer.

```python
class DataClassification(str, Enum):
    INTERNAL = "internal"  # non-public, no regulatory label
    SENSITIVE = "sensitive"  # NDA / contractual confidentiality
    PII = "pii"  # GDPR/CCPA — requires DPA
    PHI = "phi"  # HIPAA — requires BAA
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
    "PHI/REGULATED require Bedrock-Anthropic with AWS BAA (EE, operator-configured).",
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
    notes="Default: plain OpenAI API (api.openai.com, no BAA). "
    "INTERNAL + SENSITIVE cleared. PHI/REGULATED require Azure OpenAI "
    "with a Microsoft BAA (operator-configured, not default).",
)
```

**Cleared**: `INTERNAL`, `SENSITIVE`
**Not cleared by default**: `PII`, `PHI`, `REGULATED`

**Note on a prior correction**: this declaration previously listed `PHI`
and `REGULATED` as cleared, reflecting the *maximum achievable* posture if an
operator configured Azure OpenAI + a Microsoft BAA. That was inconsistent with
every other adapter's default-posture convention and with `AdapterCapabilities`'s
own documented semantics (`compliance` = what the *default* backend is
certified for). The router's `clears()` membership check is a static
class-attribute lookup with no way to verify an operator actually configured
Azure — so the old declaration risked routing PHI/REGULATED workloads to a
plain `api.openai.com` backend with no BAA. Narrowed to match
`ClaudeCodeAdapter`/`GeminiCliAdapter` below.

**Rationale**:
- Plain `api.openai.com` does not offer a BAA or PCI-DSS certification;
  `INTERNAL` and `SENSITIVE` data can be routed here by default.
- Azure OpenAI Service with a Microsoft HIPAA BAA covers `PHI`, and Azure's
  PCI-DSS Level 1 / FedRAMP High / ISO 27001 / SOC 2 certifications can cover
  `REGULATED` workloads — but this requires an operator to configure an Azure
  OpenAI endpoint, which is not this adapter's default deployment. Per the
  router's routing-policy design, that escalation is meant to be expressed as a
  per-backend `compliance: [...]` override in `routing.yaml` (router-owned),
  layered on top of this adapter-level default — not a static class attribute
  here.
- `PII` remains undeclared for the same reason as before: no default backend
  in this table offers a GDPR DPA at standard tier.

---

### `GeminiCliAdapter`

```python
capabilities = AdapterCapabilities.for_levels(
    DataClassification.INTERNAL,
    DataClassification.SENSITIVE,
    notes="Default: Google Cloud Gemini API (no HIPAA BAA at standard tier). "
    "INTERNAL + SENSITIVE cleared. PHI/REGULATED require Google Cloud "
    "Healthcare-certified deployment (operator-configured, not default).",
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
    "Google Cloud Healthcare-certified project (operator-configured).",
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
| `OpenAIAgentsAdapter` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `GeminiCliAdapter` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `GeminiApiAdapter` | ✅ | ✅ | ❌ | ❌ | ❌ |

All four adapters now declare identical *default*-posture semantics: no
adapter's default backend is cleared for `PII`, `PHI`, or `REGULATED`.

**For PHI/REGULATED workloads**, the router is expected to select a backend
via an operator-configured `routing.yaml` per-backend `compliance` override
(e.g. an Azure-OpenAI-configured `OpenAIAgentsAdapter` deployment, a
Bedrock-Anthropic deployment, or a self-hosted vLLM adapter) — not via any
adapter's static default declaration.

---

## Implementation notes

- `capabilities` is a **class-level attribute** (not instance-level), declared
  directly on the class body.  Instances inherit it; the object is shared.
- `AdapterCapabilities` is a frozen dataclass — immutable after construction.
- The `SkillAdapter` Protocol is NOT updated to require `capabilities` — this
  is a forward-compatible addition.  Once `otaman-core` publishes
  `AdapterCapabilities` and the router starts reading it, the Protocol will be
  extended in `otaman-core`.

---

## Where to find this in code

| File | What |
|---|---|
| `src/otaman_adapters/capabilities.py` | `DataClassification`, `AdapterCapabilities` types |
| `src/otaman_adapters/claude_code.py` | `ClaudeCodeAdapter.capabilities` |
| `src/otaman_adapters/openai_agents.py` | `OpenAIAgentsAdapter.capabilities` |
| `src/otaman_adapters/gemini.py` | `GeminiCliAdapter.capabilities`, `GeminiApiAdapter.capabilities` |
| `tests/test_capabilities.py` | 40 tests covering all declarations |
