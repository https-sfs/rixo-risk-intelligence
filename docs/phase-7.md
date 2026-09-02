# Phase 7 — Evaluation (in progress)

Phase 1–4B remain the locked development baseline. Evaluation is built on top of that system and does not change detector, tools, reasoner, actions, API, or frontend behavior.

## Step 2 — Held-out artifacts

| Item | Value |
| --- | --- |
| Evaluation seed | `2027` |
| Output directory | `data/heldout/` |
| Development seed (locked) | `42` |
| Development artifacts | `data/transactions.csv` and sibling detection files |

This is a **second generated world**, not a random row split of the seed-42 file. The generator calendar and scenario windows are unchanged; only the random seed differs.

### How the artifacts were generated

From the repository root, using existing generator and detector functions (no copied generation/detection logic):

```powershell
.\backend\.venv\Scripts\python.exe -m evaluation
```

That writes:

- `data/heldout/transactions.csv`
- `data/heldout/dataset_meta.json`
- `data/heldout/detected_spikes.csv`
- `data/heldout/detected_spikes.json`
- `data/heldout/hourly_windows.csv`

Equivalent explicit calls already supported by Phase 1:

```powershell
.\backend\.venv\Scripts\python.exe -m data.generate_dataset --seed 2027 --output-dir data/heldout
.\backend\.venv\Scripts\python.exe -m detection.run_detection --input data/heldout/transactions.csv --output data/heldout/detected_spikes.csv --windows-output data/heldout/hourly_windows.csv
```

`tools/paths.py` still points at the locked seed-42 files. Evaluation code must pass held-out paths explicitly.

Step 2 does **not** compute precision, recall, F1, classification scores, exposure, or intervention effectiveness.

## Step 3 — Hour-level ground truth and detection metrics

Evaluation unit: **hourly windows** in `data/heldout/hourly_windows.csv` (seed 2027 only).

Ground truth comes from `data/scenarios.py` calendars, not from detector output and not from `fraud_label`:

| Label | Rule |
| --- | --- |
| `coordinated_abuse` | hour start is inside an `AttackSpec` window |
| `legitimate_festive` | hour start is inside the festive sale calendar and is not an attack hour |
| `background` | all other hours |

Predictions are the detector's `spike_type` on those same held-out windows (`ordinary`, `legitimate_festive_spike`, `suspicious_coordinated_spike`).

Festive positives are **sale-calendar hours**, including low-volume night hours. The generator does not expose a separate “festive surge” flag. `event_type` is not used for this mapping; it remains hidden synthetic metadata.

```powershell
.\backend\.venv\Scripts\python.exe -m evaluation.detection
```

Writes `data/heldout/detection_metrics.json`. Does not rewrite seed-42 artifacts.
