from __future__ import annotations

import json

import pytest

from agent.errors import LLMOutputError, LLMProviderError
from agent.facts import extract_reasoning_facts
from agent.investigate import investigate_spike
from agent.prompts import build_investigation_prompt, prepare_llm_facts
from agent.providers.deterministic import DeterministicReasoner
from agent.providers.llm import LLMInvestigationProvider
from agent.validation import parse_and_validate_llm_report, validate_llm_report
from tools.evidence import build_investigation_evidence

SPIKE_ABUSE = "spk-coord-20260118-02"
SPIKE_FESTIVE = "spk-fest-20260114-18"


class FakeLLMClient:
    """Test double. Returns controlled text and does not call a real model."""

    def __init__(self, body: object) -> None:
        self.body = body

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if isinstance(self.body, Exception):
            raise self.body
        if isinstance(self.body, str):
            return self.body
        return json.dumps(self.body)


def _facts(spike_id: str = SPIKE_ABUSE) -> dict:
    return extract_reasoning_facts(build_investigation_evidence(spike_id))


def _valid_payload(facts: dict) -> dict:
    subnet = facts["concentration"]["subnets"][0]
    return {
        "spike_id": facts["spike_id"],
        "verdict": "coordinated_abuse",
        "confidence": 0.81,
        "summary": "Multiple supplied concentration signals support coordination.",
        "supporting_evidence": [
            {
                "fact": f"Declined rate is {facts['window']['status_rates']['declined']}",
                "source": "window.status_rates",
            },
            {
                "fact": (
                    f"Subnet {subnet['entity_id']} holds "
                    f"{subnet['share_of_transactions']} of transactions"
                ),
                "source": "concentration.subnets",
            },
        ],
        "contradicting_evidence": [],
        "key_entities": [
            {
                "entity_type": "subnet",
                "entity_id": subnet["entity_id"],
                "reason": "Dominant subnet from deterministic evidence",
            }
        ],
        "reasoning": "Several independent supplied signals align; volume alone is not treated as proof.",
        "recommended_action": {
            "type": "review",
            "scope": f"subnet {subnet['entity_id']}",
            "reason": "Narrow analyst review of the concentrated subnet.",
        },
        "human_approval_required": True,
        "limitations": [
            "labelled-fraud rate is delayed ground truth; unavailable at decision time"
        ],
    }


def test_prompt_does_not_contain_event_type() -> None:
    prompt = build_investigation_prompt(_facts())
    assert "event_type" not in prompt


def test_prompt_does_not_contain_raw_ledger_rows() -> None:
    prompt = build_investigation_prompt(_facts())
    assert "transaction_id" not in prompt
    assert "transactions.csv" not in prompt
    assert "legitimate_purchase" not in prompt
    assert "festive_purchase" not in prompt


def test_prompt_marks_labelled_fraud_as_delayed_ground_truth() -> None:
    facts = _facts()
    prompt = build_investigation_prompt(facts)
    prepared = prepare_llm_facts(facts)
    assert "delayed ground truth; unavailable at decision time" in prompt
    assert prepared["window"]["fraud_label_rate"]["interpretation"] == (
        "delayed ground truth; unavailable at decision time"
    )
    assert prepared["window"]["fraud_label_rate"]["live_signal"] is False


def test_valid_structured_llm_response_parses() -> None:
    facts = _facts()
    report = parse_and_validate_llm_report(json.dumps(_valid_payload(facts)), facts)
    assert report.verdict == "coordinated_abuse"
    assert report.human_approval_required is True
    assert report.provider == "llm"
    result = investigate_spike(
        SPIKE_ABUSE,
        provider=LLMInvestigationProvider(client=FakeLLMClient(_valid_payload(facts))),
    )
    assert result["provider"] == "llm"
    assert result["report"]["verdict"] == "coordinated_abuse"


def test_invalid_verdict_is_rejected() -> None:
    facts = _facts()
    payload = _valid_payload(facts)
    payload["verdict"] = "confirmed_fraud"
    with pytest.raises(LLMOutputError, match="Invalid verdict"):
        validate_llm_report(payload, facts)


def test_confidence_outside_range_is_rejected() -> None:
    facts = _facts()
    payload = _valid_payload(facts)
    payload["confidence"] = 1.4
    with pytest.raises(LLMOutputError, match="confidence"):
        validate_llm_report(payload, facts)
    payload["confidence"] = -0.1
    with pytest.raises(LLMOutputError, match="confidence"):
        validate_llm_report(payload, facts)


def test_nonexistent_evidence_citation_is_rejected() -> None:
    facts = _facts()
    payload = _valid_payload(facts)
    payload["supporting_evidence"] = [
        {"fact": "Invented metric", "source": "window.imaginary_metric"}
    ]
    with pytest.raises(LLMOutputError, match="Citation source does not exist"):
        validate_llm_report(payload, facts)


def test_nonexistent_entity_citation_is_rejected() -> None:
    facts = _facts()
    payload = _valid_payload(facts)
    payload["key_entities"] = [
        {
            "entity_type": "device",
            "entity_id": "dev_does_not_exist",
            "reason": "invented device",
        }
    ]
    with pytest.raises(LLMOutputError, match="does not exist"):
        validate_llm_report(payload, facts)


def test_unsupported_action_is_rejected() -> None:
    facts = _facts()
    payload = _valid_payload(facts)
    payload["recommended_action"]["type"] = "block"
    with pytest.raises(LLMOutputError, match="Unsupported action"):
        validate_llm_report(payload, facts)
    payload["recommended_action"]["type"] = "disable_account"
    with pytest.raises(LLMOutputError, match="Unsupported action"):
        validate_llm_report(payload, facts)


def test_human_approval_required_cannot_become_false() -> None:
    facts = _facts()
    payload = _valid_payload(facts)
    payload["human_approval_required"] = False
    with pytest.raises(LLMOutputError, match="human_approval_required"):
        validate_llm_report(payload, facts)


def test_missing_api_key_fails_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    provider = LLMInvestigationProvider()
    with pytest.raises(LLMProviderError, match="LLM_API_KEY"):
        provider.reason(_facts())


def test_malformed_model_json_fails_safely() -> None:
    facts = _facts()
    provider = LLMInvestigationProvider(client=FakeLLMClient("this is not json"))
    with pytest.raises(LLMOutputError, match="malformed JSON"):
        provider.reason(facts)


def test_deterministic_provider_remains_functional() -> None:
    result = investigate_spike(SPIKE_ABUSE)
    assert result["provider"] == "deterministic_reasoner"
    assert result["report"]["verdict"] == "coordinated_abuse"
    festive = investigate_spike(SPIKE_FESTIVE, provider=DeterministicReasoner())
    assert festive["provider"] == "deterministic_reasoner"
    assert festive["report"]["verdict"] == "likely_festive"


def test_llm_fallback_is_labelled_deterministic() -> None:
    provider = LLMInvestigationProvider(client=FakeLLMClient(LLMProviderError("unavailable")))
    with pytest.raises(LLMProviderError):
        investigate_spike(SPIKE_ABUSE, provider=provider)
    result = investigate_spike(
        SPIKE_ABUSE,
        provider=provider,
        fallback_to_deterministic=True,
    )
    assert result["provider"] == "deterministic_reasoner"
    assert result["report"]["provider"] == "deterministic_reasoner"
