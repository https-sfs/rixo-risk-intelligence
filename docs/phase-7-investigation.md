# Phase 7 Step 4 — Investigation evaluation

Held-out seed **2027** only. Existing deterministic reasoner. This step measures the investigator; it does not change it.

## Evaluation unit

One **detected spike** from `data/heldout/detected_spikes.csv`.
A spike may cover one or more clock hours. Expected verdict is derived from those covered hours, not from the detector `spike_type`.

## Ground truth

Reuse Step 3 scenario calendars (`evaluation/labels.py`):

- any coordinated-abuse hour → expected `coordinated_abuse`
- else any festive-sale hour → expected `likely_festive`
- else background hours only → expected `inconclusive`
- coordinated and festive hours in the same spike → `ambiguous` (not scored)

`event_type` and delayed `fraud_label` are not investigation evidence. `event_type` is hidden evaluation metadata only.

- Detected spikes evaluated: 40
- Objectively evaluable: 40
- Correct / incorrect / ambiguous: 34 / 6 / 0
- Accuracy (evaluable cases): 0.85

| Class | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| coordinated_abuse | 1.0 | 1.0 | 1.0 |
| likely_festive | 0.823529 | 1.0 | 0.903226 |
| inconclusive | None | 0.0 | None |

Incorrect evaluable cases:

- `spk-fest-20260109-07` expected `inconclusive`, actual `likely_festive` (detector `legitimate_festive_spike`)
- `spk-fest-20260109-16` expected `inconclusive`, actual `likely_festive` (detector `legitimate_festive_spike`)
- `spk-fest-20260110-19` expected `inconclusive`, actual `likely_festive` (detector `legitimate_festive_spike`)
- `spk-fest-20260110-20` expected `inconclusive`, actual `likely_festive` (detector `legitimate_festive_spike`)
- `spk-fest-20260110-21` expected `inconclusive`, actual `likely_festive` (detector `legitimate_festive_spike`)
- `spk-fest-20260111-17` expected `inconclusive`, actual `likely_festive` (detector `legitimate_festive_spike`)

## Evidence grounding

- Citations valid: 40 / 40
- Entities grounded: 40 / 40
- event_type absent: 40 / 40
- fraud_label marked delayed: 40 / 40
- Reports with supporting evidence: 6
- Reports with contradicting evidence: 34

## Recommendation policy

- Human approval required: 40
- Allowed actions: 40
- Forbidden actions: 0
- Festive tighten_rule: 0
- Proposal policy ok: 40

## Latency (engineering benchmark, not model accuracy)

- Total evaluation seconds: 2.301701
- Mean / median / max seconds: 9.3e-05 / 7.9e-05 / 0.000277

Run: `python -m evaluation.investigation`

