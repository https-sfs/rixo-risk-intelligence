# Architecture

Fraud-Spike Investigator is an **AI Risk Investigation & Governed Response** system.

It is not an autonomous payment blocker. The operator loop is:

**DETECT → EVIDENCE → CLASSIFIER EVIDENCE → REASONING → DECISION → HUMAN APPROVAL → SIMULATION → AUDIT**

The larger product loop is:

**DETECT → INVESTIGATE → DECIDE → ACT → VERIFY**

`ACT` means a **simulated** payment-system operation after explicit human approval.

## End-to-end

```
Payment / transaction telemetry
        ↓
Risk ML + temporal anomaly detection
        ↓
Evidence + provenance
        ↓
Investigation Intelligence
        ↓
Read-only investigation tools
        ↓
Reasoning
        ↓
Governed decision
        ↓
Human approval
        ↓
Simulation / Razorpay TEST
        ↓
Audit + durable governance state
```

## Classifier vs detector

```
Transaction data
    ├── supervised fraud-risk classifier
    │       └── supporting evidence
    │
    └── independent anomaly detector
            └── anomaly detection
```

Both feed investigation. Classifier output is **not** the cause of the anomaly, **not** a fraud confirmation, and **not** an action authorization.

`decide_from_investigation()` uses live anomaly signals. Classifier `high_risk_count` is recorded as supporting evidence with `used_for_action_selection: false`.

## Layers

| Layer | Location | Responsibility |
| --- | --- | --- |
| Operator UI | `frontend/` | Four-world console; 4-stage governance workspace |
| API | `backend/app/` | World-isolated HTTP surface |
| Synthetic data | `data/` | Seed-42 demo ledger and seed-2027 holdout |
| Detection | `detection/`, `evaluation/*/detect.py` | World-specific anomaly detection |
| Classifier | `models/ieee_fraud/` | Shared IEEE-CIS fraud-risk model |
| Evidence tools | `tools/` | Deterministic window facts (synthetic) |
| Intelligence | `evaluation/intelligence.py` | Pass 1: structured case evidence |
| Investigator | `agent/investigator.py` | Pass 2: read-only five-tool plan |
| Reasoners | `agent/providers/` | Deterministic default; optional fail-closed LLM narrator |
| Governance | `agent/actions/`, `evaluation/*/governance.py` | Decide → approve → simulate → audit |
| Persistence | `backend/app/persistence.py` | One SQLite file behind existing stores |
| Razorpay TEST | `backend/app/integrations/` | Sandbox adapter after approval only |

Deterministic code produces facts. The investigator inspects those facts. It does not execute actions.

## Four isolated worlds

| World | Store | Routes |
| --- | --- | --- |
| SYNTHETIC SCENARIO | `ActionStore` | `/`, `/api/spikes` |
| REAL PUBLIC DATA (IEEE-CIS) | `RealActionStore` | `/real`, `/api/real` |
| RECENT PUBLIC DATA (January 2026) | `RecentActionStore` | `/recent`, `/api/recent` |
| BRING YOUR DATA | session `CustomActionStore` | `/bring`, `/api/custom` |

Stores do not share proposals, approvals, simulations, or idempotency keys. SQLite rows always include an explicit `world` column. BYOD remains session-scoped and is not process-durable.

## Investigation Intelligence (Pass 1)

`evaluation/intelligence_worlds.py` builds a per-case blob from **existing artifacts**:

- brief (flagged / observed / derived / uncertain / next checks)
- temporal neighbors
- entities or explicit missing identifiers
- same-world baseline
- provenanced case metrics
- operational false-positive impact (no ₹ saved)
- classifier evidence-quality status

No rescan of raw ledgers.

## Investigation Agent (Pass 2)

`agent/investigator.py` is a bounded tool caller, not a chatbot.

Fixed plan: case metrics → temporal → entities → baseline → classifier evidence → structured finding.

The investigator uses a deterministic fixed read-only tool plan (`deterministic_tool_plan`) rather than LLM tool calling. This preserves reproducibility, bounded behavior, four-world isolation, and governance separation. The investigator is not an autonomous decision-maker.

It does not import ActionStore, approve, simulate, or Razorpay.

## Governance

```
Investigation report / anomaly evidence
        ↓
Decision (record)
        ↓
Proposal
        ↓
Human approval
        ↓
Simulation (Razorpay TEST after approval)
        ↓
Audit
```

Human approval is mandatory. Simulation before approval returns **409**.

IEEE propose accepts an optional `idempotency_key`. Same key + same fingerprint replays. Same key + different request is a **409** conflict. Proposal + key + audit event commit in one SQLite transaction.

## Razorpay TEST

The adapter is **TEST / SIMULATION only**.

- Demonstrates the corresponding payment-system operation
- Does not execute a live payment
- Does not move real money
- Does not require keys for the rest of the investigation workflow

This is not a live production Razorpay integration.

## Durable persistence

`GovernanceDB` (`sqlite3`) sits **behind** the existing stores. Default file: `data/governance.sqlite`.

Startup loads state. It does not approve, simulate, or call Razorpay.

## Operator routes

| Path | Page |
| --- | --- |
| `/` | Synthetic overview |
| `/investigations/:spikeId` | Synthetic case |
| `/real` / `/real/anomalies/:id` | IEEE-CIS |
| `/recent` / `/recent/anomalies/:id` | January 2026 |
| `/bring` | Bring Your Data |
| `/actions`, `/audit` | Synthetic session/audit views |

The UI cannot skip approval or treat classifier output as a block.

## Constraints

- Facts come from deterministic artifacts, not generated essays
- Unavailable identifiers stay unavailable
- Delayed labels are evaluation-only
- IEEE in-sample overlays are CONTEXTUAL, not test accuracy
- January classifier metrics are not calculated
- No money-saved / ROI claims
- No autonomous action
- No second persistence store
- Formal synthetic spike-level evaluation lives in `evaluation/scorecard.py`
- Controlled synthetic counterfactual outcome measurement lives in `evaluation/counterfactual.py` and is separate from Decision → Approval → Simulation → Audit
- IEEE intervention effectiveness is not measurable as genuine before/after production performance
- LLM tool calling is an intentional deterministic-agent tradeoff, not a missing feature

Historical phase notes in `docs/phase-*.md` describe earlier increments. This file is the current architecture.
