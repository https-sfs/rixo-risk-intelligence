# IEEE-CIS supervised fraud-risk artifacts

This directory holds **MODEL PREDICTION** artifacts for the IEEE-CIS world only.

## Evaluation protocol

- Chronological split on `TransactionDT`: **70% train / 10% validation / 20% test**. No shuffle.
- Earlier transactions always precede later transactions.
- Categorical mappings are **fit on train only**. Unseen validation/test categories map to NaN.
- High-cardinality string columns (nunique > 255 on train) use a deterministic per-value hash. No validation/test vocabulary is learned.
- Class weights are computed from **train labels only**.
- The operating threshold is selected on **validation only** (maximum F1 over the documented sweep) and then **frozen**.
- PR-AUC, ROC-AUC, precision, recall, F1, confusion, and calibration under `test` are the **untouched temporal test set**.
- Validation F1 is a threshold-selection statistic, not an untouched test result.

## Feature leakage rules

- Target is `isFraud`. It is never a model feature.
- `TransactionID` is not a model feature.
- Forbidden source-model fields: `fraud_probability`, `risk_level`, `confidence`, `recommendation`.
- January 2026 source-model fields are forbidden. This model is not trained on or applied to seed-42 or January 2026.

## Inference

`ieee_hgb.joblib` is a bundle: fitted `HistGradientBoostingClassifier` + train-fit encoder + frozen threshold. `encoder.json` is the inspectable encoder sidecar. Do not recompute category codes from a combined dataframe.

Train locally (raw CSVs stay gitignored):

```
.\backend\.venv\Scripts\python.exe -m models.ieee_fraud.pipeline
```

`model_evaluation.json` and `hour_risk_overlay.json` are committable evaluation artifacts.

These metrics are historical IEEE-CIS test results. They are not production performance, money saved, or a live payment decision.
