# Recent public data — January 2026 online-banking export

This directory is the **RECENT PUBLIC DATA** world.

It is **not** the seed-42 synthetic demo and **not** the IEEE-CIS REAL PUBLIC DATA world.

| World | Location | Role |
| --- | --- | --- |
| Synthetic demo | `data/` seed 42 | Controlled festive / coordinated-abuse demo |
| Real public data | `data/real/` | IEEE-CIS Fraud Detection benchmark |
| Recent public data | `data/real_2026/` (this directory) | January 2026 Zenodo online-banking export |

`tools/paths.py` remains pointed at seed 42. IEEE-CIS adapters remain under `evaluation/real_data/`.

## Provenance

- **Title:** A Production-Collected Online Banking Fraud Detection Dataset from a Live Cloud-Based Deep Learning System
- **Authors:** Hemn Hashim Fatah, Zryan Najat Rashed (Sulaimani Polytechnic University)
- **Zenodo record:** [20359708](https://zenodo.org/records/20359708) (v5)
- **Concept DOI:** [10.5281/zenodo.20030064](https://doi.org/10.5281/zenodo.20030064)
- **Record DOI:** [10.5281/zenodo.20359708](https://doi.org/10.5281/zenodo.20359708)
- **Licence:** Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Collection period (source):** 1–31 January 2026
- **Source note:** collected via a public demonstration API (`model-test.online`), **not** licensed-bank customer traffic

This repository does **not** download the dataset. Place the official CSV here manually.

## Expected published collection (source README)

- 56,962 transactions
- 98 confirmed fraudulent (`is_fraud = 1`)
- 0.172% fraud rate
- Amounts described by the source as **USD**

## What this file actually contains

The downloaded file `fraud_tests_export_20260501_080333.csv` was inspected, not assumed.

- **40 columns** (source README describes 38)
- Extra columns vs README: `id`, `test_date`
- **57,394 rows** in the export
- Rows with `test_date` set: **56,962** / **98** fraud — this is the official January collection used for analysis
- Rows without `test_date`: **432** (April–May 2026 timestamps) — profiled, excluded from primary metrics
- `response_time_ms` is described by the source and is **absent** from this export
- `time_value` in this file is a Unix timestamp, not the README’s 0–172,792 elapsed-second field
- `ip_address` is present; January IPs are unique per row, so they do not support repeat-entity concentration

## Transaction fields vs source-model outputs

**Transaction / metadata fields (usable as observed or derived inputs):**
`transaction_id`, `amount`, `time_value`, `timestamp`, `test_date`, `ip_address`, `v1`–`v28`, `is_fraud`

**Source dataset model outputs (never our predictions, scores, labels, or metrics):**
`fraud_probability`, `risk_level`, `confidence`, `recommendation`

`v1`–`v28` are PCA features from the source schema. They are not interpreted as SKU, merchant, device, or transaction type.

`is_fraud` is delayed/historical ground truth with source verification bias (only BLOCK-flagged rows were reviewed). It is never a live detector input.

## Historical public data

This is historical public research data. It is **not** our live production traffic and not a payment-execution environment.

Raw CSVs are gitignored and must not be committed.
