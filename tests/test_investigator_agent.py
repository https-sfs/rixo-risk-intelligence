"""Bounded tool-calling investigator. Evidence only. No chatbot. No governance."""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.actions.service import default_store, reset_default_store
from agent.investigate import investigate_spike
from agent.investigator import PLAN, investigate_with_tools
from agent.investigator_tools import (
    TOOL_NAMES,
    TOOLS,
    InvestigatorToolError,
    inspect_classifier_evidence,
    run_tool,
)
from app.main import app
from evaluation.intelligence import (
    BYOD_WORLD,
    IEEE_WORLD,
    JANUARY_WORLD,
    STATUS_LIMITED,
    SYNTHETIC_WORLD,
)
from evaluation.intelligence_worlds import for_custom, for_ieee, for_january, for_synthetic

REPO = Path(__file__).resolve().parent.parent
AGENT_DIR = REPO / "agent"
client = TestClient(app)

FORBIDDEN = (
    "confirmed fraud",
    "fraud confirmed",
    "classifier detected",
    "classifier caused",
    "authorizes the action",
    "execute this",
)
LEDGER_NAMES = ("train_transaction.csv", "transactions.csv", "fraud_tests_export")


def _blob(value: object) -> str:
    return json.dumps(value, default=str).lower()


def _assert_no_forbidden(payload: dict) -> None:
    text = _blob(payload)
    for phrase in FORBIDDEN:
        assert phrase not in text
    assert "execute x" not in text
    finding = str(payload.get("finding") or "").lower()
    assert "high risk proves" not in finding


def _minimal_worlds() -> dict[str, dict]:
    return {
        SYNTHETIC_WORLD: for_synthetic(
            {"spike": {"spike_id": "s-iso"}, "window": {"transaction_count": 4}, "classifier": {}}
        ),
        JANUARY_WORLD: for_january(
            {"anomaly_id": "j-iso", "hour_start": "2026-01-04T20:00:00", "transactions": 4, "signals": []},
            {"live_evidence": {"transaction_count": {"value": 4}}, "classifier": {}},
        ),
        IEEE_WORLD: for_ieee(
            {"anomaly_id": "i-iso", "relative_hour_bucket": 2, "transactions": 3, "signals": ["volume"]},
            {"live_evidence": {"transaction_count": {"value": 3}}, "classifier": {}},
        ),
        BYOD_WORLD: for_custom(
            {"anomaly_id": "c-iso", "hour_start": "2026-03-02T04:00:00", "transactions": 8, "signals": []},
            {"live_evidence": {"transaction_count": {"value": 8}}, "classifier": {}},
            mapped_roles=["amount", "timestamp"],
        ),
    }


def test_tool_registry_is_explicit_and_read_only() -> None:
    assert TOOL_NAMES == (
        "inspect_case_metrics",
        "inspect_temporal_context",
        "inspect_entities",
        "inspect_historical_baseline",
        "inspect_classifier_evidence",
    )
    assert set(TOOLS) == set(TOOL_NAMES)
    intel = _minimal_worlds()[SYNTHETIC_WORLD]
    for name in TOOL_NAMES:
        result = run_tool(name, intel, world=SYNTHETIC_WORLD)
        assert result["read_only"] is True
        assert result["tool"] == name
        assert result["status"] == "completed"
        assert result["world"] == SYNTHETIC_WORLD
        source = inspect.getsource(TOOLS[name])
        assert "open(" not in source
        assert "write" not in source
        assert "ActionStore" not in source


def test_unknown_tools_are_rejected() -> None:
    intel = _minimal_worlds()[SYNTHETIC_WORLD]
    with pytest.raises(InvestigatorToolError, match="Unknown investigation tool"):
        run_tool("invent_entities", intel)
    with pytest.raises(InvestigatorToolError, match="Unknown investigation tool"):
        run_tool("approve_action", intel)


def test_four_world_tool_calls_cannot_cross_read() -> None:
    worlds = _minimal_worlds()
    for actual_world, intel in worlds.items():
        for requested in worlds:
            if requested == actual_world:
                result = run_tool("inspect_entities", intel, world=requested)
                assert result["world"] == actual_world
                continue
            with pytest.raises(InvestigatorToolError, match="belongs to"):
                run_tool("inspect_entities", intel, world=requested)
            with pytest.raises(InvestigatorToolError, match="belongs to"):
                run_tool("inspect_case_metrics", intel, world=requested)
        agent = investigate_with_tools(intel)
        assert agent["world"] == actual_world
        for other_world, other_intel in worlds.items():
            if other_world == actual_world:
                continue
            assert agent["case_id"] != other_intel.get("case_id")
            assert agent["world"] != other_world


def test_tool_output_preserves_provenance() -> None:
    intel = for_synthetic(
        {
            "spike": {"spike_id": "spk-coord-20260118-02", "window_start": "2026-01-18T02:00:00", "anomaly_reasons": []},
            "window": {"transaction_count": 10},
            "classifier": {"status": "not_scored"},
        }
    )
    metrics = run_tool("inspect_case_metrics", intel)
    assert metrics["provenance"]
    for item in metrics["metrics"]:
        assert item.get("provenance")
        assert item.get("source")
    temporal = run_tool("inspect_temporal_context", intel)
    if temporal["available"]:
        assert temporal["provenance"]
    classifier = run_tool("inspect_classifier_evidence", intel)
    assert classifier["provenance"] == "MODEL PREDICTION"
    assert classifier["used_for_action_selection"] is False
    assert classifier["not_fraud_confirmed"] is True


def test_missing_entities_and_baselines_stay_unavailable() -> None:
    january = for_january(
        {"anomaly_id": "rct-x", "hour_start": "2026-01-04T20:00:00", "transactions": 10, "signals": []},
        {
            "live_evidence": {"transaction_count": {"value": 10}},
            "classifier": {"status": "scored", "feature_coverage": 0.004},
            "evaluation_overlay": {"fraud_count": 1},
        },
    )
    entities = run_tool("inspect_entities", january)
    baseline = run_tool("inspect_historical_baseline", january)
    assert entities["available"] is False
    assert "account" in entities["missing"]
    assert entities["groups"] == {} or not entities["available"]
    assert any("unavailable" in item.lower() for item in entities["limitations"])
    assert baseline["same_world_only"] is True
    byod = for_custom(
        {"anomaly_id": "cda-x", "hour_start": "2026-03-02T04:00:00", "transactions": 80, "signals": []},
        {"live_evidence": {"transaction_count": {"value": 80}}, "classifier": {"status": "not_scored"}},
        mapped_roles=["amount", "timestamp"],
    )
    missing = run_tool("inspect_entities", byod)
    assert missing["available"] is False
    assert "account_id" in missing["missing"]
    agent = investigate_with_tools(january)
    text = _blob(agent)
    assert "unavailable" in text
    assert "dev_" not in json.dumps(entities.get("groups") or {})


def test_classifier_score_cannot_strengthen_the_finding() -> None:
    intel = for_synthetic(
        {
            "spike": {
                "spike_id": "spk-x",
                "spike_type": "suspicious_coordinated_spike",
                "window_start": "2026-01-18T02:00:00",
                "anomaly_reasons": ["ip_subnet_concentration"],
            },
            "window": {"transaction_count": 10},
            "classifier": {
                "status": "scored",
                "feature_coverage": 0.0139,
                "fraud_risk_score": 0.2,
                "high_risk_count": 1,
                "classification": "Low risk",
            },
        }
    )
    original = investigate_with_tools(intel)
    mutated = copy.deepcopy(intel)
    mutated["classifier_status"]["fraud_risk_score"] = 0.99
    mutated["classifier_status"]["high_risk_count"] = 10_000
    mutated["classifier_status"]["scored_rows"] = 10_000
    mutated["classifier_status"]["classification"] = "High risk"
    boosted = investigate_with_tools(mutated)
    assert original["finding"] == boosted["finding"]
    assert "0.99" not in boosted["finding"]
    assert "10000" not in boosted["finding"].replace(",", "")
    clf = inspect_classifier_evidence(mutated)
    assert clf["used_for_action_selection"] is False
    assert clf["not_fraud_confirmed"] is True


def test_festive_case_18_stays_limited_supporting_evidence() -> None:
    body = client.get("/api/spikes/spk-fest-20260114-18/investigation").json()
    agent = body["investigation_agent"]
    intel = body["investigation_intelligence"]
    report = body["report"]
    clf = next(step for step in [run_tool("inspect_classifier_evidence", intel)])
    assert intel["classifier_status"]["status"] == STATUS_LIMITED
    assert 0.01 < float(intel["classifier_status"]["feature_coverage"]) < 0.02
    assert intel["classifier_status"]["high_risk_count"] == 91
    assert intel["classifier_status"]["scored_rows"] == 91
    assert clf["evidence_quality"] == STATUS_LIMITED
    assert clf["used_for_action_selection"] is False
    assert clf["not_fraud_confirmed"] is True
    assert report["recommended_action"]["type"] == "monitor"
    _assert_no_forbidden(agent)
    assert "confirmed fraud" not in _blob(agent)
    assert agent["not_a_governance_decision"] is True
    assert agent["does_not_authorize_action"] is True
    assert "execute" not in str(agent.get("recommended_next_human_check") or "").lower()


def test_investigator_cannot_change_action_store_or_select_actions() -> None:
    reset_default_store()
    before = dict(default_store().proposals)
    result = investigate_spike("spk-fest-20260114-18")
    assert dict(default_store().proposals) == before
    client.get("/api/spikes/spk-fest-20260114-18/investigation")
    assert dict(default_store().proposals) == before
    agent_src = (AGENT_DIR / "investigator.py").read_text(encoding="utf-8")
    tools_src = (AGENT_DIR / "investigator_tools.py").read_text(encoding="utf-8")
    for source in (agent_src, tools_src):
        assert "ActionStore" not in source
        assert "decide_from_investigation" not in source
        assert "approve_action" not in source
        assert "execute_action" not in source
        assert "propose_from_report" not in source
    assert result["investigation_agent"]["does_not_approve"] is True
    assert result["investigation_agent"]["does_not_simulate"] is True
    assert result["investigation_agent"]["does_not_authorize_action"] is True
    clf = run_tool("inspect_classifier_evidence", result["investigation_intelligence"])
    assert clf["used_for_action_selection"] is False


def test_no_conversational_endpoint_is_introduced() -> None:
    paths = [getattr(route, "path", "") for route in app.routes]
    joined = " ".join(paths).lower()
    assert "/chat" not in joined
    assert "ask-ai" not in joined
    assert "conversation" not in joined
    ui = (REPO / "frontend" / "src" / "components" / "InvestigationAgent.tsx").read_text(encoding="utf-8")
    assert "textarea" not in ui.lower()
    assert "ask ai" not in ui.lower()
    assert "chatbot" not in ui.lower()
    assert "type=" not in ui.lower() or 'type="text"' not in ui.lower()


def test_deterministic_planner_works_without_llm() -> None:
    intel = _minimal_worlds()[SYNTHETIC_WORLD]
    result = investigate_with_tools(intel)
    assert result["planner"] == "deterministic_tool_plan"
    assert result["not_an_llm_paragraph"] is True
    assert result["not_a_chatbot"] is True
    assert [step["tool"] for step in result["trace"]] == list(PLAN)
    assert all(step["status"] == "completed" for step in result["trace"])
    source = (AGENT_DIR / "investigator.py").read_text(encoding="utf-8")
    assert "openai" not in source.lower()
    assert "LLM_API_KEY" not in source
    assert "httpx" not in source
    assert "requests" not in source


def test_investigator_modules_do_not_scan_ledgers() -> None:
    combined = "".join(
        path.read_text(encoding="utf-8")
        for path in (
            AGENT_DIR / "investigator.py",
            AGENT_DIR / "investigator_tools.py",
        )
    )
    for name in LEDGER_NAMES:
        assert name not in combined
    assert "read_csv" not in combined


def test_structured_output_contract_and_evidence_used() -> None:
    result = investigate_spike("spk-coord-20260118-02")["investigation_agent"]
    for key in (
        "finding",
        "supporting_evidence",
        "contradictory_evidence",
        "uncertainty",
        "recommended_next_human_check",
        "evidence_used",
        "trace",
    ):
        assert key in result
    assert result["finding"]
    assert result["supporting_evidence"]
    for item in result["supporting_evidence"]:
        assert item.get("tool") in TOOL_NAMES
        assert item.get("provenance")
        assert item.get("statement")
    assert [item["tool"] for item in result["evidence_used"]] == list(TOOL_NAMES)
    _assert_no_forbidden(result)


def test_unknown_world_is_rejected() -> None:
    with pytest.raises(InvestigatorToolError, match="Unknown investigation world"):
        run_tool("inspect_entities", {"world": "MERGED WORLD", "entities": {}})
