"""Held-out LLM investigation evaluation.

Uses the existing LLMInvestigationProvider and Phase 2A facts only.
Does not execute actions, call payment APIs, or invent LLM answers.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from agent.errors import LLMOutputError, LLMProviderError
from agent.facts import extract_reasoning_facts
from agent.investigate import investigate_spike
from agent.prompts import build_investigation_prompt, prepare_llm_facts
from agent.providers.llm import LLMInvestigationProvider, read_llm_api_key
from agent.schema import ALLOWED_ACTIONS, FORBIDDEN_ACTIONS
from agent.validation import resolve_source
from evaluation.heldout_evidence import (
    build_heldout_evidence,
    load_heldout_hourly_windows,
    load_heldout_spikes,
    load_heldout_transactions,
    spike_record_from_row,
)
from evaluation.investigation import expected_investigation_verdict
from evaluation.metrics import class_breakdown, json_number, safe_divide
from evaluation.paths import (
    EVALUATION_SEED,
    HELDOUT_LLM_PATH,
    HELDOUT_META_PATH,
    HELDOUT_SPIKES_CSV_PATH,
    HELDOUT_TRANSACTIONS_PATH,
)

VERDICTS = ("coordinated_abuse", "likely_festive", "inconclusive")
INVESTIGATION_METRICS_PATH = Path(__file__).resolve().parent / "investigation_metrics.json"
STATUS_VALID_CORRECT = "valid_correct"
STATUS_VALID_INCORRECT = "valid_incorrect"
STATUS_AMBIGUOUS = "ambiguous_excluded"
STATUS_PROVIDER = "provider_failure"
STATUS_MALFORMED = "malformed_response"
STATUS_VALIDATION = "validation_failure"
VALID_STATUSES = (STATUS_VALID_CORRECT, STATUS_VALID_INCORRECT, STATUS_AMBIGUOUS)


def classify_llm_failure(exc: BaseException) -> str:
    if isinstance(exc, LLMOutputError):
        text = str(exc).lower()
        if "malformed json" in text or "empty output" in text or "must be an object" in text:
            return STATUS_MALFORMED
        return STATUS_VALIDATION
    if isinstance(exc, LLMProviderError):
        return STATUS_PROVIDER
    return STATUS_PROVIDER


def score_valid_verdict(expected: str, actual: str) -> tuple[bool | None, str]:
    if expected == "ambiguous":
        return None, STATUS_AMBIGUOUS
    if actual == expected:
        return True, STATUS_VALID_CORRECT
    return False, STATUS_VALID_INCORRECT


def percentile(values: list[float], q: float) -> float | None:
    if len(values) < 2:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    frac = index - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def _citations_valid(report: dict[str, Any], facts: dict[str, Any]) -> bool:
    citations = list(report.get("supporting_evidence") or []) + list(
        report.get("contradicting_evidence") or []
    )
    for item in citations:
        try:
            resolve_source(facts, str(item.get("source") or ""))
        except Exception:
            return False
    return True


def _entities_grounded(report: dict[str, Any], evidence: dict[str, Any]) -> bool:
    dumped = json.dumps(evidence)
    for entity in report.get("key_entities") or []:
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id or entity_id not in dumped:
            return False
    return True


def build_heldout_llm_prompt(spike: dict[str, Any], evidence: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Production prompt from held-out Phase 2A facts. No ledger dump."""
    _ = spike
    facts = extract_reasoning_facts(evidence)
    return build_investigation_prompt(facts), facts


def _input_boundary(prompt: str, facts: dict[str, Any]) -> dict[str, bool]:
    prepared = prepare_llm_facts(facts)
    delayed = str(prepared.get("window", {}).get("fraud_label_rate", {}).get("interpretation") or "")
    return {
        "event_type_absent": "event_type" not in prompt,
        "transaction_id_absent": "transaction_id" not in prompt,
        "ledger_path_absent": "transactions.csv" not in prompt,
        "hidden_event_values_absent": all(
            token not in prompt for token in ("festive_purchase", "legitimate_purchase")
        ),
        "fraud_label_marked_delayed": "delayed" in delayed.lower(),
        "fraud_label_not_live": prepared.get("window", {}).get("fraud_label_rate", {}).get("live_signal") is False,
    }


def not_produced_report(reason: str) -> dict[str, Any]:
    return {
        "evaluation_unit": "detected_spike",
        "heldout_seed": EVALUATION_SEED,
        "provider": "llm",
        "source": "not_produced",
        "real_llm_evaluated": False,
        "reason": reason,
        "label": "REAL LLM METRICS WERE NOT PRODUCED",
        "n_detected_spikes": 40,
        "n_attempted": 0,
        "n_valid": 0,
        "n_evaluable_valid": 0,
        "n_correct": 0,
        "n_incorrect": 0,
        "n_ambiguous": 0,
        "failure_counts": {
            STATUS_PROVIDER: 0,
            STATUS_MALFORMED: 0,
            STATUS_VALIDATION: 0,
        },
        "valid_response_rate": None,
        "accuracy": None,
        "per_class": {},
        "grounding": {},
        "safety": {},
        "latency_benchmark": {
            "label": "engineering benchmark, not model accuracy",
            "n": 0,
            "total_evaluation_seconds": None,
            "mean_seconds": None,
            "median_seconds": None,
            "p95_seconds": None,
            "max_seconds": None,
        },
        "deterministic_comparison": {
            "note": "No LLM verdicts were produced, so no comparison was computed.",
        },
        "cases": [],
        "limitations": [
            "Real LLM evaluation requires LLM_API_KEY in the process environment.",
            "This artifact does not fabricate model verdicts.",
            "The normal test suite uses an injected fake client labeled MOCK.",
        ],
        "not_calculated": [
            "money_saved",
            "loss_prevented",
            "roi",
            "intervention_effectiveness",
        ],
    }


def evaluate_heldout_llm(
    *,
    client: Any | None = None,
    mode: str = "real",
    spike_ids: list[str] | None = None,
) -> dict[str, Any]:
    meta = json.loads(HELDOUT_META_PATH.read_text(encoding="utf-8"))
    seed = int(meta["seed"])
    if seed != EVALUATION_SEED:
        raise ValueError(f"LLM evaluation requires held-out seed {EVALUATION_SEED}, got {seed}")
    heldout_tx = str(HELDOUT_TRANSACTIONS_PATH.resolve()).replace("\\", "/")
    if "/heldout/" not in heldout_tx:
        raise ValueError("LLM evaluation must not read seed-42 transactions")

    if mode not in {"real", "mock"}:
        raise ValueError("mode must be 'real' or 'mock'")
    if mode == "mock" and client is None:
        raise ValueError("MOCK LLM evaluation requires an injected test client")
    if mode == "real" and client is not None:
        raise ValueError("Real LLM evaluation must not use an injected client")
    if mode == "real" and not read_llm_api_key():
        return not_produced_report("LLM_API_KEY is not configured")

    provider = LLMInvestigationProvider(client=client) if client is not None else LLMInvestigationProvider()
    spikes = load_heldout_spikes()
    transactions = load_heldout_transactions()
    if "event_type" in transactions.columns:
        raise ValueError("Held-out LLM evidence must not include event_type")
    hourly = load_heldout_hourly_windows()
    wanted = set(spike_ids) if spike_ids is not None else None

    step4_verdicts: dict[str, str] = {}
    if INVESTIGATION_METRICS_PATH.is_file():
        step4 = json.loads(INVESTIGATION_METRICS_PATH.read_text(encoding="utf-8"))
        for case in step4.get("cases") or []:
            step4_verdicts[str(case["spike_id"])] = str(case["actual_verdict"])

    started = time.perf_counter()
    cases: list[dict[str, Any]] = []
    latencies: list[float] = []

    for _, row in spikes.iterrows():
        spike = spike_record_from_row(row)
        if wanted is not None and spike["spike_id"] not in wanted:
            continue
        expected = expected_investigation_verdict(spike["window_start"], spike["window_end"])
        evidence = build_heldout_evidence(spike, transactions, hourly)
        prompt, facts = build_heldout_llm_prompt(spike, evidence)
        boundary = _input_boundary(prompt, facts)
        if not boundary["event_type_absent"]:
            raise ValueError("event_type leaked into the LLM prompt")

        t0 = time.perf_counter()
        try:
            result = investigate_spike(
                spike["spike_id"],
                provider=provider,
                evidence=evidence,
                fallback_to_deterministic=False,
            )
            latency = time.perf_counter() - t0
            latencies.append(latency)
            if result["provider"] != "llm":
                raise LLMProviderError("LLM evaluation refused a non-LLM provider result")
            report = result["report"]
            correct, status = score_valid_verdict(expected, str(report["verdict"]))
            action_type = str((report.get("recommended_action") or {}).get("type") or "")
            cases.append(
                {
                    "spike_id": spike["spike_id"],
                    "expected_verdict": expected,
                    "actual_verdict": report["verdict"],
                    "status": status,
                    "correct": correct,
                    "evaluable": expected != "ambiguous",
                    "provider": result["provider"],
                    "citations_valid": _citations_valid(report, result["facts_used"]),
                    "entities_grounded": _entities_grounded(report, evidence),
                    "human_approval_required": report.get("human_approval_required") is True,
                    "allowed_action": action_type in ALLOWED_ACTIONS,
                    "forbidden_action": action_type in FORBIDDEN_ACTIONS,
                    "recommended_action": report.get("recommended_action"),
                    "deterministic_verdict": step4_verdicts.get(spike["spike_id"]),
                    "input_boundary": boundary,
                    "latency_seconds": round(latency, 6),
                    "failure_message": None,
                }
            )
        except (LLMOutputError, LLMProviderError) as exc:
            latency = time.perf_counter() - t0
            latencies.append(latency)
            status = classify_llm_failure(exc)
            cases.append(
                {
                    "spike_id": spike["spike_id"],
                    "expected_verdict": expected,
                    "actual_verdict": None,
                    "status": status,
                    "correct": None,
                    "evaluable": expected != "ambiguous",
                    "provider": "llm",
                    "citations_valid": False,
                    "entities_grounded": False,
                    "human_approval_required": False,
                    "allowed_action": False,
                    "forbidden_action": False,
                    "recommended_action": None,
                    "deterministic_verdict": step4_verdicts.get(spike["spike_id"]),
                    "input_boundary": boundary,
                    "latency_seconds": round(latency, 6),
                    "failure_message": str(exc),
                }
            )

    valid = [case for case in cases if case["status"] in VALID_STATUSES]
    evaluable_valid = [case for case in valid if case["evaluable"] and case["status"] != STATUS_AMBIGUOUS]
    correct_n = sum(1 for case in evaluable_valid if case["correct"] is True)
    incorrect_n = sum(1 for case in evaluable_valid if case["correct"] is False)
    truths = [case["expected_verdict"] for case in evaluable_valid]
    preds = [case["actual_verdict"] for case in evaluable_valid]
    per_class = class_breakdown(truths, preds, VERDICTS) if evaluable_valid else {}
    elapsed = time.perf_counter() - started
    comparable = [
        case
        for case in evaluable_valid
        if case["deterministic_verdict"] is not None
    ]

    report = {
        "evaluation_unit": "detected_spike",
        "heldout_seed": seed,
        "provider": "llm",
        "source": mode,
        "real_llm_evaluated": mode == "real",
        "label": "MOCK" if mode == "mock" else "REAL_LLM",
        "n_detected_spikes": int(len(spikes)),
        "n_attempted": len(cases),
        "n_valid": len(valid),
        "n_evaluable_valid": len(evaluable_valid),
        "n_correct": correct_n,
        "n_incorrect": incorrect_n,
        "n_ambiguous": sum(1 for case in cases if case["status"] == STATUS_AMBIGUOUS),
        "failure_counts": {
            STATUS_PROVIDER: sum(1 for case in cases if case["status"] == STATUS_PROVIDER),
            STATUS_MALFORMED: sum(1 for case in cases if case["status"] == STATUS_MALFORMED),
            STATUS_VALIDATION: sum(1 for case in cases if case["status"] == STATUS_VALIDATION),
        },
        "valid_response_rate": json_number(safe_divide(len(valid), len(cases))),
        "accuracy": json_number(safe_divide(correct_n, len(evaluable_valid))),
        "per_class": {
            label: {
                **{key: per_class[label][key] for key in ("tp", "fp", "tn", "fn")},
                "precision": json_number(per_class[label]["precision"]),
                "recall": json_number(per_class[label]["recall"]),
                "f1": json_number(per_class[label]["f1"]),
            }
            for label in VERDICTS
        }
        if per_class
        else {},
        "grounding": {
            "citations_valid": sum(1 for case in valid if case["citations_valid"]),
            "entities_grounded": sum(1 for case in valid if case["entities_grounded"]),
            "n_valid": len(valid),
        },
        "safety": {
            "human_approval_required": sum(1 for case in valid if case["human_approval_required"]),
            "allowed_actions": sum(1 for case in valid if case["allowed_action"]),
            "forbidden_actions": sum(1 for case in valid if case["forbidden_action"]),
            "n_valid": len(valid),
        },
        "latency_benchmark": {
            "label": "engineering benchmark, not model accuracy",
            "n": len(latencies),
            "total_evaluation_seconds": json_number(elapsed),
            "mean_seconds": json_number(statistics.mean(latencies) if latencies else None),
            "median_seconds": json_number(statistics.median(latencies) if latencies else None),
            "p95_seconds": json_number(percentile(latencies, 0.95)),
            "max_seconds": json_number(max(latencies) if latencies else None),
        },
        "deterministic_comparison": {
            "note": "Descriptive only. Neither provider was tuned.",
            "n_comparable_valid_evaluable": len(comparable),
            "agreement_with_deterministic": json_number(
                safe_divide(
                    sum(1 for case in comparable if case["actual_verdict"] == case["deterministic_verdict"]),
                    len(comparable),
                )
            ),
        },
        "cases": cases,
        "input_contract": {
            "evidence": "held-out Phase 2A facts via evaluation.heldout_evidence",
            "prompt": "agent.prompts.build_investigation_messages",
            "not_supplied": [
                "full transaction ledger",
                "event_type",
                "hidden scenario labels as reasoning input",
                "evaluation ground-truth answers",
            ],
        },
        "limitations": [
            "Latency is an engineering measurement, not a quality score.",
            "Failures are not converted into correct/incorrect verdicts.",
            "Investigation verdicts are not ground truth; calendar labels are.",
            "MOCK results must never be mixed with REAL_LLM metrics.",
        ],
        "not_calculated": [
            "money_saved",
            "loss_prevented",
            "roi",
            "intervention_effectiveness",
        ],
        "heldout_paths": {
            "transactions": str(HELDOUT_TRANSACTIONS_PATH),
            "spikes": str(HELDOUT_SPIKES_CSV_PATH),
        },
    }
    return report


def write_llm_report(report: dict[str, Any], output_path: Path | None = None) -> Path:
    dest = output_path or HELDOUT_LLM_PATH
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return dest


def write_llm_markdown(report: dict[str, Any], output_path: Path) -> Path:
    lines = [
        "# Phase 7 — LLM investigation evaluation",
        "",
        f"Source: **{report.get('label') or report.get('source')}**. "
        f"Real LLM evaluated: **{report.get('real_llm_evaluated')}**.",
        "",
        "## Evaluation unit",
        "",
        "One held-out **detected spike**. Evidence is Phase 2A facts from `data/heldout/`.",
        "The production prompt builder and `LLMInvestigationProvider` are used unchanged.",
        "",
        "## Ground truth",
        "",
        "Locked `evaluation/labels.py` calendars, same mapping as Step 4:",
        "",
        "- any coordinated-abuse hour → `coordinated_abuse`",
        "- else any festive-sale hour → `likely_festive`",
        "- else background → `inconclusive`",
        "- mixed coordinated + festive → `ambiguous` (excluded from scored classification)",
        "",
        "`event_type` is not model input. `fraud_label` remains delayed / not live.",
        "",
        "## Failure categories",
        "",
        "- `provider_failure` — transport, timeout, or missing key at call time",
        "- `malformed_response` — empty or non-JSON model text",
        "- `validation_failure` — schema, citation, action, or approval checks",
        "- `valid_correct` / `valid_incorrect` — structured report scored against calendar GT",
        "- `ambiguous_excluded` — valid report on a mixed-window spike, not scored",
        "",
        "Failures are not converted into classification predictions.",
        "",
        "## Results",
        "",
    ]
    if not report.get("real_llm_evaluated") and report.get("source") == "not_produced":
        lines.extend(
            [
                report.get("reason") or "Real LLM metrics were not produced.",
                "",
                "No verdict counts, accuracy, or per-class scores were fabricated.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"- Attempted: {report['n_attempted']}",
                f"- Valid structured reports: {report['n_valid']}",
                f"- Valid-response rate: {report['valid_response_rate']}",
                f"- Evaluable valid: {report['n_evaluable_valid']}",
                f"- Correct / incorrect / ambiguous: {report['n_correct']} / {report['n_incorrect']} / {report['n_ambiguous']}",
                f"- Accuracy on valid evaluable cases: {report['accuracy']}",
                f"- Failures: {report['failure_counts']}",
                "",
            ]
        )
        if report.get("per_class"):
            lines.extend(
                [
                    "| Class | Precision | Recall | F1 |",
                    "| --- | ---: | ---: | ---: |",
                ]
            )
            for label, scores in report["per_class"].items():
                lines.append(
                    f"| {label} | {scores['precision']} | {scores['recall']} | {scores['f1']} |"
                )
            lines.append("")
        latency = report["latency_benchmark"]
        lines.extend(
            [
                "## Latency (engineering benchmark)",
                "",
                f"- n: {latency['n']}",
                f"- Total evaluation seconds: {latency['total_evaluation_seconds']}",
                f"- Mean / median / p95 / max: {latency['mean_seconds']} / {latency['median_seconds']} / {latency['p95_seconds']} / {latency['max_seconds']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Limitations",
            "",
            "- No money-saved, prevented-loss, or ROI metrics.",
            "- Comparison with the deterministic Step 4 investigator is descriptive only.",
            "- MOCK and REAL_LLM results must not be mixed.",
            "",
            "Run real evaluation: `python -m evaluation.llm`",
            "",
            "Requires `LLM_API_KEY` in the process environment. The test suite uses a fake client.",
            "",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Held-out LLM investigation evaluation.")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Refuse unless a test injects a client. Official CLI mock is not a silent substitute.",
    )
    args = parser.parse_args(argv)
    if args.mock:
        print(
            "MOCK mode on the CLI does not invent a client. "
            "Inject a test double in code, or run without --mock using LLM_API_KEY.",
            file=sys.stderr,
        )
        report = not_produced_report("CLI --mock does not fabricate LLM answers")
        report["source"] = "mock"
        report["label"] = "MOCK"
        write_llm_report(report)
        write_llm_markdown(
            report,
            Path(__file__).resolve().parent.parent / "docs" / "phase-7-llm.md",
        )
        return 2

    report = evaluate_heldout_llm(mode="real")
    write_llm_report(report)
    write_llm_markdown(
        report,
        Path(__file__).resolve().parent.parent / "docs" / "phase-7-llm.md",
    )
    printable = {key: value for key, value in report.items() if key != "cases"}
    print(json.dumps(printable, indent=2))
    if not report.get("real_llm_evaluated"):
        print(report.get("reason") or "Real LLM metrics were not produced.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
