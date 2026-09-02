from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tools.evidence import build_investigation_evidence
from tools.load import INVESTIGATION_COLUMNS, filter_window, load_spike_transactions
from tools.paths import TRANSACTIONS_PATH

SPIKE_CARD = "spk-coord-20260118-02"
SPIKE_DEVICE = "spk-coord-20260108-13"
TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"


def _independent_window(spike_id: str) -> tuple[pd.Series, pd.DataFrame]:
    spikes = pd.read_csv(Path(TRANSACTIONS_PATH).parent / "detected_spikes.csv")
    spike = spikes.loc[spikes["spike_id"] == spike_id].iloc[0]
    start = pd.Timestamp(spike["window_start"])
    end = pd.Timestamp(spike["window_end"])
    txs = pd.read_csv(TRANSACTIONS_PATH)
    txs["timestamp"] = pd.to_datetime(txs["timestamp"])
    window = txs.loc[(txs["timestamp"] >= start) & (txs["timestamp"] < end)].copy()
    window["pincode"] = window["pincode"].astype(str)
    return spike, window


def test_card_testing_spike_counts_match_csv() -> None:
    expected_spike, expected = _independent_window(SPIKE_CARD)
    spike, window = load_spike_transactions(SPIKE_CARD)
    evidence = build_investigation_evidence(SPIKE_CARD)

    assert len(window) == len(expected) == 75
    assert evidence["window"]["transaction_count"] == len(expected)
    assert evidence["window"]["total_amount"] == round(float(expected["amount"].sum()), 2)
    assert evidence["window"]["mean_amount"] == round(float(expected["amount"].mean()), 2)
    assert evidence["entities"]["unique_accounts"] == int(expected["account_id"].nunique())
    assert evidence["entities"]["unique_devices"] == int(expected["device_id"].nunique())
    assert evidence["entities"]["unique_subnets"] == int(expected["ip_subnet"].nunique())
    assert evidence["entities"]["unique_skus"] == int(expected["sku_id"].nunique())
    assert spike["window_start"] == pd.Timestamp(expected_spike["window_start"])


def test_device_farm_spike_counts_match_csv() -> None:
    _, expected = _independent_window(SPIKE_DEVICE)
    evidence = build_investigation_evidence(SPIKE_DEVICE)
    assert evidence["window"]["transaction_count"] == len(expected)
    assert evidence["window"]["total_amount"] == round(float(expected["amount"].sum()), 2)


def test_half_open_window_excludes_end() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-01-18T02:00:00", "2026-01-18T02:59:59", "2026-01-18T03:00:00"]
            )
        }
    )
    filtered = filter_window(
        frame,
        pd.Timestamp("2026-01-18T02:00:00"),
        pd.Timestamp("2026-01-18T03:00:00"),
    )
    assert len(filtered) == 2
    assert pd.Timestamp("2026-01-18T03:00:00") not in set(filtered["timestamp"])


def test_status_rates_match_csv() -> None:
    _, expected = _independent_window(SPIKE_CARD)
    evidence = build_investigation_evidence(SPIKE_CARD)
    count = len(expected)
    for status in ("success", "failed", "declined"):
        observed = int((expected["transaction_status"] == status).sum())
        assert evidence["window"]["status_counts"][status] == observed
        assert evidence["window"]["status_rates"][status] == round(observed / count, 4)


def test_top_concentration_matches_csv() -> None:
    _, expected = _independent_window(SPIKE_CARD)
    evidence = build_investigation_evidence(SPIKE_CARD)
    top_device = expected["device_id"].value_counts().index[0]
    top_subnet = expected["ip_subnet"].value_counts().index[0]
    top_sku = expected["sku_id"].value_counts().index[0]
    assert evidence["concentration"]["devices"][0]["entity_id"] == str(top_device)
    assert evidence["concentration"]["subnets"][0]["entity_id"] == str(top_subnet)
    assert evidence["concentration"]["skus"][0]["entity_id"] == str(top_sku)
    assert evidence["concentration"]["devices"][0]["transaction_count"] == int(
        expected["device_id"].value_counts().iloc[0]
    )


def test_missing_volume_baseline_is_explicit() -> None:
    evidence = build_investigation_evidence(SPIKE_DEVICE)
    volume = evidence["baseline_comparison"]["hourly_baseline"]["baseline_volume"]
    ratio = evidence["baseline_comparison"]["hourly_baseline"]["volume_change_ratio"]
    assert volume["value"] is None
    assert volume["status"] == "unavailable"
    assert "unavailable" in volume["reason"]
    assert volume["value"] != 0
    assert ratio["value"] is None
    assert ratio["status"] == "unavailable"


def test_available_volume_baseline_is_not_null() -> None:
    expected_spike, _ = _independent_window(SPIKE_CARD)
    evidence = build_investigation_evidence(SPIKE_CARD)
    volume = evidence["baseline_comparison"]["hourly_baseline"]["baseline_volume"]
    assert pd.notna(expected_spike["baseline_volume"])
    assert volume["status"] == "available"
    assert volume["value"] == round(float(expected_spike["baseline_volume"]), 4)


def test_event_type_is_not_used_by_investigation_tools() -> None:
    for path in TOOLS_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "event_type" not in source
    assert "event_type" not in INVESTIGATION_COLUMNS
    evidence = build_investigation_evidence(SPIKE_CARD)
    dumped = json.dumps(evidence)
    assert "event_type" not in dumped
    assert "festive_purchase" not in dumped
    assert "coordinated_abuse" not in dumped
    assert "legitimate_purchase" not in dumped


def test_fraud_label_is_marked_delayed_ground_truth() -> None:
    _, expected = _independent_window(SPIKE_CARD)
    evidence = build_investigation_evidence(SPIKE_CARD)
    labelled = evidence["window"]["fraud_label_rate"]
    assert labelled["value"] == round(float(expected["fraud_label"].mean()), 4)
    assert "delayed ground truth" in labelled["interpretation"]
    assert "not a live score" in labelled["interpretation"]


def test_evidence_is_json_serializable() -> None:
    evidence = build_investigation_evidence(SPIKE_CARD)
    encoded = json.dumps(evidence)
    decoded = json.loads(encoded)
    assert decoded["spike"]["spike_id"] == SPIKE_CARD
    assert decoded["window"]["transaction_count"] > 0
