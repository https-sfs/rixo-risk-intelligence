from __future__ import annotations

import json
import re
from pathlib import Path

from agent.facts import extract_reasoning_facts
from agent.investigate import investigate_spike
from agent.policy import enforce_report_policy
from agent.providers.deterministic import DeterministicReasoner
from agent.providers.llm import UnconfiguredLLMProvider
from agent.schema import (
    ALLOWED_ACTIONS,
    FORBIDDEN_ACTIONS,
    InvestigationReport,
    RecommendedAction,
)
from tools.evidence import build_investigation_evidence

SPIKE_ABUSE = "spk-coord-20260118-02"
SPIKE_MISSING_VOLUME = "spk-coord-20260108-13"
SPIKE_FESTIVE = "spk-fest-20260114-18"
AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"
REQUIRED_REPORT_KEYS = {
    "spike_id",
    "verdict",
    "confidence",
    "summary",
    "supporting_evidence",
    "contradicting_evidence",
    "key_entities",
    "reasoning",
    "recommended_action",
    "human_approval_required",
}


def _report(spike_id: str, evidence=None) -> dict:
    result = investigate_spike(spike_id, evidence=evidence)
    return result["report"]


def _lookup(payload: dict, dotted: str):
    current = payload
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _assert_citations_grounded(report: dict, evidence: dict) -> None:
    dumped = json.dumps(evidence)
    citations = report["supporting_evidence"] + report["contradicting_evidence"]
    for item in citations:
        assert _lookup(evidence, item["source"]) is not None, item["source"]
        for token in re.findall(r"\b(?:dev_|sku_|acc_)[A-Za-z0-9_]+|\d+\.\d+\.\d+\.0/24\b", item["fact"]):
            assert token in dumped, token
        for number in re.findall(r"\d+\.\d+", item["fact"]):
            assert number in dumped or number.rstrip("0") in dumped
    for entity in report["key_entities"]:
        assert entity["entity_id"] in dumped


def test_strong_coordinated_evidence_can_produce_coordinated_abuse() -> None:
    report = _report(SPIKE_ABUSE)
    assert report["verdict"] == "coordinated_abuse"
    assert report["supporting_evidence"]
    assert 0.0 <= report["confidence"] <= 1.0


def test_legitimate_festive_evidence_can_produce_likely_festive() -> None:
    report = _report(SPIKE_FESTIVE)
    assert report["verdict"] == "likely_festive"
    assert report["contradicting_evidence"]


def test_ambiguous_evidence_can_produce_inconclusive() -> None:
    evidence = build_investigation_evidence(SPIKE_FESTIVE)
    evidence["window"]["status_rates"]["failed"] = 0.40
    evidence["window"]["status_rates"]["declined"] = 0.0
    evidence["window"]["status_rates"]["success"] = 0.60
    evidence["concentration"]["skus"][0]["share_of_transactions"] = 0.55
    report = _report(SPIKE_FESTIVE, evidence=evidence)
    assert report["verdict"] == "inconclusive"
    assert report["supporting_evidence"]
    assert report["contradicting_evidence"]


def test_missing_volume_baseline_is_acknowledged() -> None:
    evidence = build_investigation_evidence(SPIKE_MISSING_VOLUME)
    result = investigate_spike(SPIKE_MISSING_VOLUME, evidence=evidence)
    report = result["report"]
    text = " ".join(
        [
            report["reasoning"],
            report["summary"],
            *report.get("limitations", []),
        ]
    ).lower()
    assert evidence["baseline_comparison"]["hourly_baseline"]["baseline_volume"]["status"] == (
        "unavailable"
    )
    assert "unavailable" in text
    assert "baseline" in text
    assert "15.341" not in text
    assert report["reasoning"].count("x the hour-of-day baseline") == 0


def test_evidence_values_cannot_be_invented() -> None:
    evidence = build_investigation_evidence(SPIKE_ABUSE)
    result = investigate_spike(SPIKE_ABUSE, evidence=evidence)
    _assert_citations_grounded(result["report"], evidence)
    facts = result["facts_used"]
    assert facts["window"]["transaction_count"] == evidence["window"]["transaction_count"]
    assert facts["entities"] == evidence["entities"]


def test_event_type_is_not_passed_as_live_reasoning_evidence() -> None:
    for path in AGENT_DIR.rglob("*.py"):
        assert "event_type" not in path.read_text(encoding="utf-8")
    result = investigate_spike(SPIKE_ABUSE)
    assert "event_type" not in json.dumps(result["facts_used"])
    assert "event_type" not in json.dumps(result["report"])
    assert "festive_purchase" not in json.dumps(result["facts_used"])
    assert "coordinated_abuse" not in json.dumps(result["facts_used"]).replace(
        result["report"]["verdict"], ""
    )


def test_fraud_label_is_marked_delayed_ground_truth() -> None:
    evidence = build_investigation_evidence(SPIKE_ABUSE)
    result = investigate_spike(SPIKE_ABUSE, evidence=evidence)
    label = result["facts_used"]["window"]["fraud_label_rate"]
    assert "delayed ground truth" in label["interpretation"]
    text = " ".join(result["report"].get("limitations", []) + [result["report"]["reasoning"]])
    assert "delayed ground truth" in text
    assert "not a live score" in label["interpretation"]


def test_recommended_actions_always_require_human_approval() -> None:
    for spike_id in (SPIKE_ABUSE, SPIKE_FESTIVE, SPIKE_MISSING_VOLUME):
        report = _report(spike_id)
        assert report["human_approval_required"] is True
        assert report["recommended_action"]["type"] in ALLOWED_ACTIONS


def test_no_unrestricted_block_action_exists() -> None:
    report = InvestigationReport.from_dict(_report(SPIKE_ABUSE))
    report.recommended_action = RecommendedAction(
        type="block",  # type: ignore[arg-type]
        scope="all transactions",
        reason="should be rejected",
    )
    try:
        enforce_report_policy(report)
        raised = False
    except ValueError:
        raised = True
    assert raised
    for spike_id in (SPIKE_ABUSE, SPIKE_FESTIVE, SPIKE_MISSING_VOLUME):
        action = _report(spike_id)["recommended_action"]["type"]
        assert action not in FORBIDDEN_ACTIONS
        assert action in ALLOWED_ACTIONS
        assert action != "block"


def test_output_is_valid_structured_json() -> None:
    result = investigate_spike(SPIKE_ABUSE)
    encoded = json.dumps(result["report"])
    decoded = json.loads(encoded)
    assert REQUIRED_REPORT_KEYS <= set(decoded)
    assert decoded["verdict"] in {"coordinated_abuse", "likely_festive", "inconclusive"}
    assert isinstance(decoded["supporting_evidence"], list)
    assert decoded["recommended_action"]["type"] in ALLOWED_ACTIONS
    assert decoded["human_approval_required"] is True
    InvestigationReport.from_dict(decoded)


def test_reasoner_is_not_a_fake_llm_call() -> None:
    assert DeterministicReasoner.name == "deterministic_reasoner"
    result = investigate_spike(SPIKE_ABUSE)
    assert result["provider"] == "deterministic_reasoner"
    assert result["evidence_source"] == "phase_2a_deterministic"
    try:
        UnconfiguredLLMProvider().reason(extract_reasoning_facts(build_investigation_evidence(SPIKE_ABUSE)))
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "API key" in str(exc) or "configured" in str(exc)
    assert raised


def test_synthetic_reasoner_does_not_consume_classifier_facts() -> None:
    evidence = build_investigation_evidence(SPIKE_ABUSE)
    result = investigate_spike(SPIKE_ABUSE, evidence=evidence)
    dumped_facts = json.dumps(result["facts_used"])
    dumped_report = json.dumps(result["report"])
    assert "classifier" not in result["facts_used"]
    assert "fraud_risk_score" not in dumped_facts
    assert "Classifier output is available as supporting evidence" not in dumped_report
    assert result.get("classifier") is not None
    festive = investigate_spike(SPIKE_FESTIVE)
    assert festive["report"]["recommended_action"]["type"] == "monitor"
    assert "Classifier output is available as supporting evidence" not in festive["report"]["reasoning"]
    assert "Classifier output is available as supporting evidence" not in festive["report"]["summary"]


def test_reasoner_does_not_load_the_ledger() -> None:
    reasoner = (AGENT_DIR / "providers" / "deterministic.py").read_text(encoding="utf-8")
    facts = (AGENT_DIR / "facts.py").read_text(encoding="utf-8")
    for source in (reasoner, facts):
        assert "transactions.csv" not in source
        assert "read_csv" not in source
        assert "NetworkX" not in source
