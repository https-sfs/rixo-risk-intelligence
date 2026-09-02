# IEEE-CIS Fraud Detection — real public data

This directory is the **REAL PUBLIC DATA BENCHMARK** workspace.

It is **not** the synthetic product world.

| World | Location | Role |
| --- | --- | --- |
| Synthetic demo | `data/transactions.csv` (seed 42) | Reproducible product demo |
| Held-out evaluation | `data/heldout/` (seed 2027) | Synthetic evaluation artifacts |
| Real public data | `data/real/` (this directory) | Optional IEEE-CIS benchmark only |

`tools/paths.py` remains pointed at the seed-42 synthetic ledger. IEEE-CIS is a **separate** investigation world (`/real`, `/api/real`). It does not replace synthetic, January 2026, or Bring Your Data files.

## Dataset

- **Name:** IEEE-CIS Fraud Detection
- **Source:** Kaggle / Vesta
- **License / redistribution:** terms belong to Kaggle and Vesta. Obtain the dataset yourself and respect those terms. This repository does not redistribute the raw files.

## Obtain the files manually

This project **does not download** IEEE-CIS.

There is no bundled download URL and no automatic fetch.

1. Accept the IEEE-CIS Fraud Detection competition / dataset terms on Kaggle.
2. Download the official archive yourself.
3. Place the extracted CSVs in this directory (`data/real/`).

## Expected raw files

Required for a labelled benchmark:

- `train_transaction.csv`

Optional, used only for device-identity coverage (DeviceType / DeviceInfo):

- `train_identity.csv`

The official transaction amount column is `TransactionAmt` (USD). The adapter also accepts `TransactionAMT` if present.

Do **not** place these files under `data/` next to `transactions.csv`. Do **not** overwrite any synthetic or held-out artifact.

## Raw files are not committed

Raw IEEE-CIS CSVs (and archives) are gitignored. Do not commit them.

Raw CSVs stay gitignored. Derived artifacts (`anomalies.json`, `evidence.json`, hourly metrics, model overlay / evaluation JSON) may be committed so the IEEE world can run without rescanning the ledger.

## What this dataset is not

IEEE-CIS is a public fraud-classification table. It does **not** provide:

- real IP addresses or IP subnets
- success / failed / declined payment status
- real SKU identity
- a festive / Diwali / sale calendar
- AttackSpec or coordinated-abuse ground truth

`TransactionDT` is relative elapsed time, not a calendar date. `isFraud` is a delayed evaluation label, not live evidence.
