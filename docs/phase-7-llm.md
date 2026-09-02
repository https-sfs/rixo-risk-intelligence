# Phase 7 — LLM investigation evaluation

Source: **REAL LLM METRICS WERE NOT PRODUCED**. Real LLM evaluated: **False**.

## Evaluation unit

One held-out **detected spike**. Evidence is Phase 2A facts from `data/heldout/`.
The production prompt builder and `LLMInvestigationProvider` are used unchanged.

## Ground truth

Locked `evaluation/labels.py` calendars, same mapping as Step 4:

- any coordinated-abuse hour → `coordinated_abuse`
- else any festive-sale hour → `likely_festive`
- else background → `inconclusive`
- mixed coordinated + festive → `ambiguous` (excluded from scored classification)

`event_type` is not model input. `fraud_label` remains delayed / not live.

## Failure categories

- `provider_failure` — transport, timeout, or missing key at call time
- `malformed_response` — empty or non-JSON model text
- `validation_failure` — schema, citation, action, or approval checks
- `valid_correct` / `valid_incorrect` — structured report scored against calendar GT
- `ambiguous_excluded` — valid report on a mixed-window spike, not scored

Failures are not converted into classification predictions.

## Results

LLM_API_KEY is not configured

No verdict counts, accuracy, or per-class scores were fabricated.

## Limitations

- No money-saved, prevented-loss, or ROI metrics.
- Comparison with the deterministic Step 4 investigator is descriptive only.
- MOCK and REAL_LLM results must not be mixed.

Run real evaluation: `python -m evaluation.llm`

Requires `LLM_API_KEY` in the process environment. The test suite uses a fake client.

