# Synthetic transaction data

This folder holds the Phase 1 merchant transaction dataset used to exercise detection.

`fraud_label` is ground truth for later evaluation. It is not a live fraud score and is not a payment decision.

## Scenarios in the generated file

1. **Normal baseline traffic** — diverse customers, devices, IPs, pincodes, and SKUs, with ordinary velocity and mostly successful checkouts.
2. **Legitimate festive/seasonal sale** — a clearly higher-volume shopping period that stays geographically and behaviourally diverse. Higher volume alone is not abuse.
3. **Coordinated abuse clusters** — at least two injected campaigns with shared infrastructure, concentrated geography/SKUs, unusual velocity, and weaker success rates. Relationships are intentional so a later graph investigation can recover them.

Isolated labelled-fraud rows can appear in normal and festive traffic. Those rows are not a coordinated campaign.

## Files

| File | Purpose |
| --- | --- |
| `transactions.csv` | Primary dataset |
| `dataset_meta.json` | Seed, size, and date range |
| `generate_dataset.py` | Reproducible generator |

Regenerate from the repository root:

```powershell
python -m data.generate_dataset
```

The generator uses a fixed seed so two runs produce the same file.
