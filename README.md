# Fraud-Spike Investigator

## AI Risk Investigation & Governed Response for Razorpay

Transaction ML risk scoring plus independent anomaly detection, then investigation, evidence/provenance, reasoning, human-governed action, simulation, and audit.

This is **not** an autonomous fraud blocker. It is a risk-investigation and response workflow:

**DETECT → INVESTIGATE → DECIDE → ACT → VERIFY**

A conventional stack often stops at `transaction → fraud score → block`. This system keeps the classifier as supporting evidence and requires a human before any simulated payment-system action.

---

## 1. Problem

Payment-risk teams do not only need a score. They need to know **why a window looks abnormal**, what evidence supports or contradicts that reading, what a human should inspect next, and what bounded action would be taken — without silently blocking live payments.

A high model score is not a fraud confirmation. A festive surge is not coordinated abuse. Delayed labels arrive after the decision window. Those distinctions are easy to collapse in a dashboard and expensive to get wrong.

## 2. Why this matters for Razorpay / payment risk teams

Razorpay-style merchant risk operations need:

- a way to investigate spikes without treating every score as a block
- an evidence trail a human can challenge
- an action path that cannot fire without approval
- a simulation of the corresponding payment-system operation before anything live

This demo uses **controlled investigation worlds** and **Razorpay TEST / SIMULATION** behavior. No live Razorpay payment action is performed. No real money is moved. Human approval is required before a simulated action. Razorpay TEST Mode demonstrates the corresponding payment-system operation without affecting real payments.

The architecture is designed so payment telemetry can feed investigation later, while **action execution stays governed**.

## 3. Our solution

An operator console over four isolated investigation worlds. For a detected case the system:

1. Shows live anomaly evidence and delayed labels separately
2. Attaches classifier output as **supporting evidence**, with an explicit quality status
3. Builds Investigation Intelligence from existing artifacts (no ledger rescan)
4. Runs a **read-only** five-tool investigation agent
5. Records a deterministic decision
6. Waits for human approval
7. Simulates the action (Razorpay TEST adapter when configured)
8. Writes an audit trail and durable governance state

## 4. Core innovation

The classifier is **not** the sole decision-maker and is **not** the anomaly detector.

```
transaction telemetry
  → independent anomaly detection
  → evidence collection
  → provenance
  → classifier supporting evidence
  → structured investigation
  → hypothesis / evidence inspection
  → governed recommendation
  → human approval
  → simulation
  → audit
```

Versus a conventional path:

```
transaction → fraud score → block
```

**Delayed ground truth** (`isFraud` / user labels) is evaluation-only. It is not a live detector input and not an action authorization.

Classifier **coverage and status** are first-class: `UNAVAILABLE`, `LIMITED`, `TRANSFERRED`, `CONTEXTUAL`, `SUPPORTED`. A high score with ~1.4% feature coverage stays `LIMITED`. An IEEE in-sample overlay stays `CONTEXTUAL` — not held-out accuracy, not production performance.

## 5. End-to-end workflow

Operator-facing loop:

**DETECT → EVIDENCE → CLASSIFIER EVIDENCE → REASONING → DECISION → HUMAN APPROVAL → SIMULATION → AUDIT**

Larger product loop:

**DETECT → INVESTIGATE → DECIDE → ACT → VERIFY**

`ACT` in this repository means **simulated** action after explicit approval. It does not mean a live payment block.

## 6. Architecture

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

Classifier branch (explicit):

```
Transaction data
    ├── supervised fraud-risk classifier
    │       └── supporting evidence
    │
    └── independent anomaly detector
            └── anomaly detection
```

Both feed investigation. Classifier output is **not** described as the cause of the anomaly.

See [docs/architecture.md](docs/architecture.md).

## 7. Four investigation worlds

Worlds are isolated. Results are **not** directly comparable.

| World | Route | What it is | Important limits |
| --- | --- | --- | --- |
| **Synthetic Investigation** | `/` | Seed-42 demo: festive vs coordinated spikes | Labels and attack calendars are scenario constructs |
| **IEEE-CIS** | `/real` | Public Vesta/Kaggle fraud table | Relative time (`TransactionDT`), no real IPs, ProductCD derived, card4 is a proxy |
| **January 2026** | `/recent` | Zenodo online-banking public export | Hour-level volume/amount only; **classifier metrics are not calculated**; source CNN-LSTM probability is not our prediction |
| **Bring Your Data** | `/bring` | Operator upload, session-scoped | User labels are evaluation-only; unmapped identifiers stay unavailable |

IEEE raw CSVs and the January raw export are **not** redistributed. Place them locally if you have license rights. Derived artifacts (`anomalies.json`, hourly metrics, model overlay) are what the app reads.

## 8. ML risk classifier

A shared IEEE-CIS HistGradientBoosting classifier (`models/ieee_fraud/`) produces transaction-level fraud-risk scores.

- Native IEEE test metrics exist (see Evaluation).
- On non-IEEE worlds the same model may be **transferred** with explicit coverage.
- Festive Case #18 is the coverage example: feature coverage ≈ **1.39%**, 91/91 scored high risk, status **LIMITED**, recommendation remains **monitor**.
- IEEE hour 2227 overlay is **`IN_SAMPLE_MODEL_OVERLAY` / CONTEXTUAL** — supporting evidence for that investigation, not a test score and not production accuracy.

The classifier never selects the IEEE/BYOD action. `used_for_action_selection` is always `false` on the evidence-quality contract.

## 9. Independent anomaly detection

Detectors run on **live observed fields** for that world (volume, amount, concentration, synthetic coordination signals). They do not use delayed fraud labels as live inputs.

Synthetic detection distinguishes `legitimate_festive_spike` from `suspicious_coordinated_spike`. High volume alone is not treated as abuse.

IEEE detection is hour-level volume/amount/ProductCD. It is **not** a trained fraud classifier and is **not** held-out model accuracy.

## 10. Investigation Intelligence

Pass 1 (`evaluation/intelligence.py`, `evaluation/intelligence_worlds.py`) attaches structured case intelligence from **cached artifacts**:

- why the case was flagged
- observed vs derived facts
- temporal neighbors
- entity relationships (or explicit unavailability)
- same-world historical baseline
- case metrics with provenance
- operational false-positive impact (**no money-saved figure**)
- classifier evidence-quality status

It does not rescan `train_transaction.csv`, `transactions.csv`, or the January raw export.

## 11. Read-only Investigation Agent

Pass 2 (`agent/investigator.py`) is **not a chatbot**. There is no Ask-AI box.

A deterministic planner always calls:

1. `inspect_case_metrics`
2. `inspect_temporal_context`
3. `inspect_entities`
4. `inspect_historical_baseline`
5. `inspect_classifier_evidence`

It returns a structured finding, uncertainty, next **human** check, and a tool trace. It cannot propose, approve, simulate, or execute. It does not replace `decide_from_investigation()`.

The investigator uses a deterministic fixed read-only tool plan rather than LLM tool calling. This preserves reproducibility, bounded behavior, four-world isolation, and governance separation. The investigator is not an autonomous decision-maker.

## 12. Evidence / provenance model

Every surfaced fact is typed. The vocabulary is existing product language, not a new invention:

| Kind | Meaning |
| --- | --- |
| **OBSERVED** | Counted from the case window |
| **DERIVED** | Computed from observed fields (scores, shares, neighbors) |
| **PROXY** | Stand-in identity (e.g. IEEE `card4`) — not a true account/card |
| **DELAYED GROUND TRUTH** | Labels available later; evaluation only |
| **MODEL PREDICTION** | Classifier / overlay score |
| **EVALUATION** | Held-out or labelled benchmark, not a live decision |
| **SCENARIO ASSUMPTION** | Operational false-positive wording; not ₹ saved |
| **UNAVAILABLE** | Identifier or baseline does not exist in that world |

Unavailable evidence is stated. It is not fabricated.

## 13. Governance and human approval

```
Decision → Approval → Simulation → Audit
```

- Decision records a bounded recommendation from **anomaly evidence**.
- Approval is a separate human step. It is never automatic.
- Simulation is gated on approval.
- The investigation agent cannot skip these gates.

IEEE propose supports an optional `idempotency_key`. Same key + same request replays the original proposal. Same key + a different anomaly/provider returns **409**. Missing key keeps the previous create-a-new-proposal behavior.

## 14. Simulation / Razorpay TEST Mode

After approval, execute/simulate calls the existing **Razorpay TEST adapter**.

- Environment is `test` only (`RAZORPAY_MODE=test`).
- If keys are absent, the workflow still completes and records that TEST integration is unavailable.
- No live payment is executed.
- No real money is moved.
- No merchant-account mutation is performed.

This is **not** a claim that a live production Razorpay integration exists.

## 15. Audit trail

Each world writes structured audit events (decision recorded, action proposed, approved, simulated). Replay of an idempotent IEEE propose does **not** duplicate `IEEE_ACTION_PROPOSED`. Restart does not emit new side-effect events.

## 16. Durable persistence

Governance state (decisions, proposals, approvals, simulations, audit, IEEE idempotency keys) is stored in **one SQLite file** behind the existing stores. Default path: `data/governance.sqlite` (`GOVERNANCE_SQLITE_PATH`).

- Explicit `world` column — no cross-world lookup
- Startup is **restore only** — no approve / simulate / Razorpay on boot
- Single-process; not a distributed lock service
- BYOD sessions remain **in-memory / upload-scoped**

There is no second ActionStore.

## 17. Evaluation / metrics

Numbers below are from committed artifacts. They are **not** production accuracy and **not** money saved.

### Synthetic spike-level scorecard (seed 42 demo)

Source: `GET /api/evaluation/synthetic` (`evaluation/scorecard.py`)

Formal window-level detection, scenario separation, investigation calendar agreement, and governance process checks on the controlled seed-42 SYNTHETIC SCENARIO ledger. In-sample for the demo world. Not held-out seed 2027, not production performance, and not mixed with IEEE classifier metrics.

### Controlled synthetic counterfactual

Source: `POST /api/evaluation/synthetic/counterfactual` (`evaluation/counterfactual.py`)

Given an already-selected seed-42 window and an already-selected bounded simulated action, measures a **CONTROLLED SYNTHETIC COUNTERFACTUAL** / **SIMULATION-ONLY OUTCOME** on an in-memory copy. It does not choose, approve, or execute an action, does not call Razorpay, and does not mutate the source ledger. Amounts are labelled **simulated fraud amount targeted/protected**, never money saved.

IEEE-CIS cannot receive these metrics. Intervention effectiveness is not measurable as genuine before/after production performance on IEEE-CIS because the dataset is historical and no post-intervention ledger exists.

### Synthetic detector holdout (seed 2027)

Source: `data/heldout/detection_metrics.json`

- Any injected scenario vs any spike: precision **0.85**, recall **0.436**
- Coordinated-abuse hours: precision/recall **1.0** (6/6)
- Festive hours: precision **0.824**, recall **0.389**
- Festive hours predicted as coordinated abuse: **0**

### Synthetic investigation (seed 2027)

Source: `evaluation/investigation_metrics.json`

- 40 detected spikes, accuracy **0.85** (34/40)
- Provider: `deterministic_reasoner`

### IEEE-CIS classifier (temporal test split)

Source: `data/real/model/model_evaluation.json`

- Chronological 70/10/20 split; `isFraud` is the target, not a feature
- Test ranking: PR-AUC **0.461861**, ROC-AUC **0.88697**
- Operating point threshold **0.5**, F1 **0.283946**
- These are **historical IEEE test results**, not production performance

### IEEE hour-level detector

Source: `data/real/evaluation.json`

- Live inputs: hour volume, amount, ProductCD share
- Temporal holdout precision is **0.0** against a delayed high-fraud-rate label
- This is **not** the classifier and **not** held-out model accuracy

### IEEE in-sample overlay

`IN_SAMPLE_MODEL_OVERLAY` on hours such as `rda-2227` is **CONTEXTUAL** supporting evidence. It is not test accuracy.

### January 2026

Source: `data/real_2026/evaluation.json`

- **Classifier metrics are not calculated**
- Source CNN-LSTM probability is not our prediction
- Hour-level detector holdout is not classifier accuracy

## 18. Safety boundaries

- TEST / SIMULATION only
- Human approval required
- No autonomous payment blocking
- No live money movement
- Classifier cannot authorize an action
- Investigator is read-only
- Four worlds never share stores or artifacts
- LLM reasoning is optional and fail-closed; the investigator uses a deterministic fixed read-only tool plan rather than LLM tool calling
- No production fraud reduction, money saved, or live payment execution is claimed

## 19. Known limitations

These are deliberate engineering boundaries, not unfinished slogans:

- Razorpay **TEST** only — no LIVE keys, no live capture/refund/block
- IEEE `TransactionDT` is relative elapsed time, not a calendar
- IEEE has no real IP/subnet, payment status, or true account identity; `card4` is a proxy
- January has no entity clustering identifiers
- January classifier metrics are intentionally not computed
- BYOD labels are evaluation-only and sessions do not survive process restart
- SQLite persistence is single-process
- Transferred classifier coverage can be very low (`LIMITED`)
- Synthetic calendars are scenario constructs
- Seed-42 scorecard is in-sample demo evaluation, not production performance
- IEEE intervention effectiveness is unavailable as genuine before/after measurement
- No money-saved / ROI figure is produced

## 20. Tech stack

| Layer | Stack |
| --- | --- |
| Operator UI | React, TypeScript, Vite |
| API | FastAPI, Pydantic |
| Governance persistence | stdlib `sqlite3` |
| Detection / intelligence | Python, pandas |
| Classifier | scikit-learn HistGradientBoosting |
| Payments demo | Razorpay TEST adapter (`httpx`) |
| Tests | pytest, Vitest |

## 21. Local setup

Prerequisites: **Node.js 20+**, **Python 3.11+**.

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

- Health: http://localhost:8000/health
- API docs: http://localhost:8000/docs

Copy `backend/.env.example` to `backend/.env` if you need to change:

- `CORS_ORIGINS` (default `http://localhost:5173`)
- `GOVERNANCE_SQLITE_PATH` (default `data/governance.sqlite`)
- `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_MODE=test` — optional TEST keys; leave empty to run without a sandbox order
- `LLM_API_KEY` — optional; deterministic investigation is the default

Never put live Razorpay keys in this project.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

Copy `frontend/.env.example` to `frontend/.env` to change `VITE_API_BASE_URL` (default `http://localhost:8000`).

### Tests and production build

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q
```

```powershell
cd frontend
npm test
npm run build
```

`npm run build` runs `tsc -b && vite build`.

### Optional synthetic regenerate

```powershell
.\backend\.venv\Scripts\python.exe -m data.generate_dataset
.\backend\.venv\Scripts\python.exe -m detection.run_detection
```

## 22. Demo flow (3–5 minutes)

**Story:** AI does not directly block a payment. AI-assisted evidence supports a governed risk workflow where humans authorize a **simulated** action.

1. Open **IEEE-CIS** → http://localhost:5173/real
2. Open **`rda-2227`** → http://localhost:5173/real/anomalies/rda-2227
3. Show the case: **748** transactions, **≈ $124.5K** observed, ProductCD **W ≈ 93.6%**, temporal anomaly
4. Show **Investigator summary** (Intelligence Pass 1)
5. Show **MODEL EVIDENCE: CONTEXTUAL** — supporting evidence, not held-out accuracy
6. Show **Investigation agent** and the five-tool trace (read-only)
7. **Record this decision** — recommendation comes from amount/volume anomaly, not from 92 high-risk rows
8. Show the **Approval** tab still gated
9. **Approve**
10. **Run dry-run simulation** — Razorpay TEST / no live payment
11. Open **Audit history** — Decision → Proposed → Approved → Simulated
12. Say that SQLite restores this state after a backend restart; it does not re-approve or re-simulate

Optional contrast: Synthetic Festive Case #18 (`/investigations/spk-fest-20260114-18`) — high volume, **LIMITED** classifier (~1.39% coverage), recommendation **monitor**.

## 23. Future roadmap

Not started, and not implied as shipped:

- Multi-instance durable storage
- Deeper Razorpay TEST objects
- Deploy / hosting packaging

**Out of scope on purpose:** chatbot, autonomous action, live Razorpay execution, money-saved claims, a second source of truth.
