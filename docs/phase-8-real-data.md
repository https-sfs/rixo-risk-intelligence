# Phase 8 — Real public data

## Phase 8.3 status

IEEE-CIS has been ingested from the locally downloaded files under `data/real/`. The API and UI now have a **REAL PUBLIC DATA** world that reads derived artifacts only.

Inspection notes (not silent workarounds):

- `isFraud` exists only on `train_transaction.csv`. Test transactions are unlabelled.
- `sample_submission.csv` `isFraud` values are 0.5 placeholders and are **not** ground truth.
- `test_identity.csv` uses `id-01` style names; device fields remain `DeviceType` / `DeviceInfo`.
- There is **no trained ML model** in this repository. Hour-level precision/recall of the volume heuristic against high-fraud hours is reported honestly and is currently 0.
- The live detector does **not** use `isFraud`. Fraud rates appear only as delayed ground truth overlays.

# Phase 8.2 — Real public data adapter

IEEE-CIS Fraud Detection is a **REAL PUBLIC DATA BENCHMARK**, not the product demo world.

| World | Path | Status |
| --- | --- | --- |
| Synthetic demo | `data/` seed 42 | Locked. Dashboard and API still use this. |
| Held-out evaluation | `data/heldout/` seed 2027 | Locked. Phase 7 artifacts unchanged. |
| Real public data | `data/real/` | Optional adapter only. Raw files are not committed. |

`tools/paths.py` remains pointed at seed 42.

## How to obtain the data

The adapter **does not download** IEEE-CIS.

Obtain the dataset manually from Kaggle / Vesta, respect the licensing and redistribution terms, and place:

- `data/real/train_transaction.csv` (required for labelled measurements)
- `data/real/train_identity.csv` (optional; device identity only)

See `data/real/README.md`. There is no bundled download URL.

## Supported fields

### Available

| Mapped name | IEEE-CIS source |
| --- | --- |
| `transaction_id` | `TransactionID` |
| `amount` | `TransactionAmt` (alias `TransactionAMT`) |
| `fraud_label` | `isFraud` (evaluation-only) |

`TransactionAmt` is **USD**. Do not display it as INR.

### Partial / proxy

| Mapped name | IEEE-CIS source | Honest meaning |
| --- | --- | --- |
| `elapsed_seconds` | `TransactionDT` | Relative elapsed time, not a calendar date |
| `relative_hour_bucket` | `floor(TransactionDT / 3600)` | Relative hour index only |
| `product` | `ProductCD` | Product code, not a SKU |
| card fields | `card1`–`card6` | Payment / card proxy |
| `account_proxy` | `card1` + `addr1` + `P_emaildomain` | Documented composite. Not `account_id`. |
| `DeviceType`, `DeviceInfo` | identity table | Present only after an identity join |
| `addr1`, `addr2` | `addr1`, `addr2` | Geographic proxy, not a pincode |

### Unavailable — never manufactured

- real IP address
- real IP subnet
- success / failed / declined transaction status
- real SKU identity
- festive calendar / Diwali / day of week
- AttackSpec / coordinated-abuse ground truth

## What this benchmark may measure

When the raw files exist:

- total transactions
- labelled fraud transactions
- fraud transaction rate
- labelled fraud amount (USD)
- hourly transaction volume by relative hour bucket
- hourly `isFraud` rate by relative hour bucket
- identity / device coverage

If the raw files are absent, the adapter fails with an instruction. It does not invent results.

## What this benchmark must not claim

Do not use IEEE-CIS for festive-vs-coordinated classification, IP subnet concentration, payment-status rates, SKU targeting, intervention effectiveness, money saved, money prevented, or ROI.

Do not reuse `evaluation/labels.py` on IEEE-CIS. Do not run the seed-2027 scenario evaluation against IEEE-CIS.

## Run

```powershell
.\backend\.venv\Scripts\python.exe -m evaluation.real_data.benchmark
```

That command reads `data/real/` only. It does not rewrite seed-42 or seed-2027 artifacts.
