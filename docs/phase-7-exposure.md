# Phase 7 Step 5 — Exposure evaluation

Held-out seed **2027** only. Observed exposure. Not money saved, prevented, or avoided.

- Transactions: 10404
- Observed amount: 14913442.89
- Mean / median / max amount: 1433.43 / 544.45 / 20335.22

## Exposure by ground-truth category

| Category | Transactions | Tx share | Amount | Amount share |
| --- | ---: | ---: | ---: | ---: |
| coordinated_abuse | 430 | 0.04133 | 1308000.51 | 0.087706 |
| legitimate_festive | 3042 | 0.292388 | 4387501.69 | 0.294198 |
| background | 6932 | 0.666282 | 9217940.69 | 0.618096 |

## Detected-spike coverage

- Transactions inside any detected spike: 2268 (0.217993)
- Amount inside any detected spike: 3894317.7 (0.261128)
- Overlapping spike window pairs: 0

## Coordinated-abuse capture

- Calendar coordinated transactions: 430
- Calendar coordinated amount: 1308000.51
- Inside detected coordinated spikes: 430 txs / 1308000.51
- Transaction capture rate: 1.0
- Amount capture rate: 1.0

## Non-coordinated surfaced exposure

- Transactions: 1838 (0.810406 of detected-spike txs)
- Amount: 2586317.19 (0.664126 of detected-spike amount)
- Surfaced legitimate festive: 1638 txs / 2323327.78
- Surfaced background: 200 txs / 262989.41

## Entity impact

Category-specific unique-entity counts are not additive.

| Category | Accounts | Devices | Subnets | Pincodes | SKUs |
| --- | ---: | ---: | ---: | ---: | ---: |
| coordinated_abuse | 217 | 86 | 26 | 34 | 40 |
| legitimate_festive | 711 | 782 | 23 | 46 | 50 |
| background | 818 | 931 | 23 | 46 | 50 |

## Detector vs investigator (descriptive)

- Detector coordinated spikes: 6 / 430 txs / 1308000.51
- Investigator coordinated_abuse verdicts: 6 / 430 txs / 1308000.51

Investigation verdicts are not ground truth. No intervention was executed.

Run: `python -m evaluation.exposure`

