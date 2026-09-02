"""Isolated tests for the IEEE-CIS supervised fraud-risk layer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from evaluation.paths import BASELINE_TRANSACTIONS_PATH, HELDOUT_TRANSACTIONS_PATH
from evaluation.real_data.detect import detect_anomalies, score_hourly
from evaluation.real_data.evidence import build_hour_metrics
from models.ieee_fraud import FORBIDDEN_FEATURES, PROVENANCE
from models.ieee_fraud.evaluate import compose_evaluation, evaluate_scores
from models.ieee_fraud.features import (
    CategoricalEncoder,
    FeatureLeakageError,
    PredictSchemaError,
    assert_no_leakage,
    build_feature_frame,
)
from models.ieee_fraud.overlay import aggregate_hour_scores
from models.ieee_fraud.pipeline import run_pipeline
from models.ieee_fraud.predict import load_model, predict_transaction, raw_frame_from_payload
from models.ieee_fraud.split import temporal_masks
from models.ieee_fraud.transfer_2026 import TransferSchemaError, transfer_status
from tools.paths import TRANSACTIONS_PATH

REPO = Path(__file__).resolve().parent.parent


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _ieee_fixture(rows: int = 240) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for index in range(rows):
        fraud = 1 if index % 12 == 0 else 0
        late = index >= int(rows * 0.85)
        records.append(
            {
                "TransactionID": index + 1,
                "isFraud": fraud,
                "TransactionDT": 10_000 + index * 200,
                "TransactionAmt": 180.0 if fraud else 22.0,
                "ProductCD": "H" if late else ("C" if fraud else "W"),
                "card1": 1111 + (index % 5),
                "card4": "visa",
                "addr1": 123.0,
                "C1": 4.0 if fraud else 0.2,
                "V1": 2.5 if fraud else -0.4,
                "fraud_probability": 99.0,
            }
        )
    return pd.DataFrame(records)


def test_feature_builder_excludes_label_and_source_model_outputs() -> None:
    features, target, meta = build_feature_frame(_ieee_fixture())
    assert target is not None
    assert int(target.sum()) > 0
    for name in FORBIDDEN_FEATURES:
        assert name not in features.columns
    assert "isFraud" not in features.columns
    assert "fraud_probability" not in features.columns
    assert_no_leakage(features)
    with pytest.raises(FeatureLeakageError):
        assert_no_leakage(pd.DataFrame({"isFraud": [0, 1]}))
    with pytest.raises(FeatureLeakageError):
        assert_no_leakage(pd.DataFrame({"risk_level": ["HIGH"]}))


def test_temporal_split_is_chronological_70_10_20_without_overlap() -> None:
    frame = _ieee_fixture()
    train, valid, test = temporal_masks(frame["TransactionDT"])
    assert int(train.sum() + valid.sum() + test.sum()) == len(frame)
    assert not (train & valid).any()
    assert not (train & test).any()
    assert not (valid & test).any()
    train_max = float(frame.loc[train, "TransactionDT"].max())
    valid_min = float(frame.loc[valid, "TransactionDT"].min())
    valid_max = float(frame.loc[valid, "TransactionDT"].max())
    test_min = float(frame.loc[test, "TransactionDT"].min())
    assert train_max < valid_min
    assert valid_max < test_min
    assert 0.65 <= train.mean() <= 0.75
    assert 0.05 <= valid.mean() <= 0.15
    assert 0.15 <= test.mean() <= 0.25


def test_encoder_fitted_only_on_train_unseen_categories_become_nan() -> None:
    features, target, meta = build_feature_frame(_ieee_fixture())
    assert target is not None
    train, valid, test = temporal_masks(meta["elapsed_seconds"])
    encoder = CategoricalEncoder().fit(features.loc[train])
    assert "H" not in encoder.mappings.get("ProductCD", {})
    valid_encoded = encoder.transform(features.loc[valid])
    test_encoded = encoder.transform(features.loc[test])
    unseen_test = features.loc[test, "ProductCD"].astype("string") == "H"
    assert unseen_test.any()
    assert test_encoded.loc[unseen_test.to_numpy(), "ProductCD"].isna().all()
    assert "H" not in set(features.loc[valid, "ProductCD"].astype(str))
    refit = CategoricalEncoder().fit(features)
    assert "H" in refit.mappings.get("ProductCD", {})
    assert encoder.mappings.get("ProductCD") != refit.mappings.get("ProductCD")


def test_metrics_use_supplied_fold_labels() -> None:
    y_train = [0, 0, 0, 1]
    y_test = [0, 1, 0, 1]
    train_scores = [0.1, 0.1, 0.1, 0.9]
    test_scores = [0.2, 0.8, 0.15, 0.85]
    train_report = evaluate_scores(y_train, train_scores, threshold=0.5)
    test_report = evaluate_scores(y_test, test_scores, threshold=0.5)
    assert train_report["n_fraud"] == 1
    assert test_report["n_fraud"] == 2
    assert test_report["ranking"]["pr_auc"] is not None
    assert test_report["ranking"]["roc_auc"] is not None
    assert test_report["confusion"]["tp"] + test_report["confusion"]["fn"] == 2


def test_threshold_selected_on_validation_never_test() -> None:
    y_valid = np.array([0, 0, 0, 0, 1, 1, 1])
    s_valid = np.array([0.05, 0.08, 0.25, 0.11, 0.32, 0.38, 0.45])
    y_test = np.array([0, 0, 1, 1])
    s_test = np.array([0.48, 0.49, 0.55, 0.9])
    validation = evaluate_scores(y_valid, s_valid)
    assert validation["threshold"] == 0.3
    test = evaluate_scores(y_test, s_test, threshold=validation["threshold"])
    test_if_selected_on_test = evaluate_scores(y_test, s_test)
    assert test["threshold"] == 0.3
    assert test_if_selected_on_test["threshold"] == 0.5
    assert test["f1"] != test_if_selected_on_test["f1"]
    report = compose_evaluation(
        validation,
        test,
        split={"kind": "temporal_chronological"},
        feature_spec_payload={"columns": []},
        preprocessing={"fitted_on": "train"},
        estimator={"type": "hgb"},
    )
    assert report["validation"]["not_an_untouched_test_result"] is True
    assert report["test"]["untouched"] is True
    assert report["test"]["threshold_source"] == "validation_frozen"
    assert report["operating_point"]["threshold"] == 0.3
    assert report["operating_point"]["f1"] == test["f1"]


def test_pipeline_trains_and_persisted_bundle_is_deterministic(tmp_path: Path) -> None:
    data_dir = tmp_path / "real"
    data_dir.mkdir()
    _ieee_fixture().drop(columns=["fraud_probability"]).to_csv(data_dir / "train_transaction.csv", index=False)
    output = tmp_path / "model"
    summary = run_pipeline(data_dir, output)
    assert (output / "ieee_hgb.joblib").is_file()
    assert (output / "encoder.json").is_file()
    assert (output / "model_evaluation.json").is_file()
    evaluation = json.loads((output / "model_evaluation.json").read_text(encoding="utf-8"))
    assert evaluation["target_used_as_feature"] is False
    assert evaluation["split"]["train_fraction"] == 0.7
    assert evaluation["split"]["validation_fraction"] == 0.1
    assert evaluation["split"]["test_fraction"] == 0.2
    assert evaluation["split"]["shuffled"] is False
    assert evaluation["test"]["untouched"] is True
    assert evaluation["test"]["threshold_source"] == "validation_frozen"
    assert evaluation["validation"]["not_an_untouched_test_result"] is True
    assert evaluation["test"]["threshold"] == evaluation["validation"]["threshold"]
    assert evaluation["preprocessing"]["fitted_on"] == "train"
    assert evaluation["estimator"]["not_an_llm"] is True
    assert summary["threshold_source"] == "validation"

    features, _, _ = build_feature_frame(pd.read_csv(data_dir / "train_transaction.csv"))
    artifact = load_model(output / "ieee_hgb.joblib")
    first = artifact.score(features)
    reloaded = load_model(output / "ieee_hgb.joblib")
    second = reloaded.score(features)
    np.testing.assert_allclose(first, second)
    assert first.min() >= 0
    assert first.max() <= 1
    encoder = json.loads((output / "encoder.json").read_text(encoding="utf-8"))
    assert encoder["fitted_on"] == "train"
    assert encoder["unseen_category_policy"] == "NaN"


def test_overlay_is_model_prediction_not_new_anomaly_type() -> None:
    scored = pd.DataFrame(
        {
            "transaction_id": [1, 2, 3, 4],
            "relative_hour_bucket": [24, 24, 25, 25],
            "fraud_risk_score": [0.9, 0.1, 0.2, 0.3],
            "amount_usd": [10.0, 4.0, 5.0, 6.0],
            "fraud_label": [1, 0, 0, 0],
        }
    )
    overlay = aggregate_hour_scores(scored, threshold=0.5)
    assert overlay["provenance"] == PROVENANCE
    assert overlay["hours"]["24"]["high_risk_count"] == 1
    assert overlay["hours"]["24"]["top_transactions"][0]["provenance"] == PROVENANCE


def test_2026_transfer_refuses_illegal_column_mapping() -> None:
    with pytest.raises(TransferSchemaError, match="v1"):
        transfer_status(["TransactionAmt", "V1"], ["amount", "v1", "v2"])
    with pytest.raises(TransferSchemaError, match="Source-model"):
        transfer_status(["TransactionAmt"], ["amount", "fraud_probability"])
    status = transfer_status(["TransactionAmt", "V1", "C1"], ["amount", "timestamp", "ip_address"])
    assert status["scored"] is False
    assert status["reason"] == "schema_mismatch"


def test_predict_refuses_synthetic_and_2026_schemas() -> None:
    with pytest.raises(PredictSchemaError, match="January 2026"):
        raw_frame_from_payload({"amount": 12.0, "v1": 0.2, "v2": -0.1, "timestamp": "2026-01-01"})
    with pytest.raises(PredictSchemaError, match="Synthetic"):
        raw_frame_from_payload({"event_type": "payment", "sku": "ABC", "pincode": "560001"})
    with pytest.raises(PredictSchemaError):
        raw_frame_from_payload({"isFraud": 1, "fraud_probability": 0.9})


def test_hour_detector_outputs_unchanged_when_model_imported() -> None:
    mapped = pd.DataFrame(
        {
            "relative_hour_bucket": [1, 1, 2, 2, 3, 3],
            "amount_usd": [10.0, 12.0, 11.0, 9.0, 80.0, 90.0],
            "product": ["W", "W", "W", "C", "W", "W"],
            "card1": [1, 1, 2, 2, 3, 3],
            "card4": ["visa"] * 6,
            "addr2": [87] * 6,
            "DeviceType": [None] * 6,
            "fraud_label": [0, 0, 0, 0, 1, 0],
        }
    )
    hourly = build_hour_metrics(mapped)
    before = score_hourly(hourly).loc[:, ["relative_hour_bucket", "live_score", "is_anomaly"]].copy()
    import models.ieee_fraud.train  # noqa: F401

    after = score_hourly(hourly).loc[:, ["relative_hour_bucket", "live_score", "is_anomaly"]]
    pd.testing.assert_frame_equal(before, after)
    detect_anomalies(hourly)


def test_locked_world_artifacts_unchanged() -> None:
    before_seed = _sha256(TRANSACTIONS_PATH)
    before_baseline = _sha256(BASELINE_TRANSACTIONS_PATH)
    before_heldout = _sha256(HELDOUT_TRANSACTIONS_PATH) if HELDOUT_TRANSACTIONS_PATH.is_file() else None
    assert _sha256(TRANSACTIONS_PATH) == before_seed
    assert _sha256(BASELINE_TRANSACTIONS_PATH) == before_baseline
    if before_heldout is not None:
        assert _sha256(HELDOUT_TRANSACTIONS_PATH) == before_heldout


def test_model_api_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.real_world as real_world

    empty = tmp_path / "empty-model"
    empty.mkdir()
    monkeypatch.setattr(real_world, "MODEL_DIR", empty)
    from app.main import app

    client = TestClient(app)
    status = client.get("/api/real/model/status")
    assert status.status_code == 200
    assert status.json()["provenance"] == PROVENANCE
    assert status.json()["ready"] is False
    missing = client.get("/api/real/model/evaluation")
    assert missing.status_code == 503
    missing_predict = client.post("/api/real/model/predict", json={"TransactionAmt": 12.0, "ProductCD": "W"})
    assert missing_predict.status_code == 503

    payload = {
        "world": "REAL PUBLIC DATA",
        "provenance": PROVENANCE,
        "ranking": {"pr_auc": 0.4, "roc_auc": 0.8},
        "operating_point": {"threshold": 0.1, "f1": 0.2},
        "target_used_as_feature": False,
    }
    (empty / "model_evaluation.json").write_text(json.dumps(payload), encoding="utf-8")
    evaluation = client.get("/api/real/model/evaluation")
    assert evaluation.status_code == 200
    assert evaluation.json()["ranking"]["pr_auc"] == 0.4
    ieee = client.get("/api/real/status")
    assert ieee.status_code == 200
    spikes = client.get("/api/spikes")
    assert spikes.status_code == 200
    recent = client.get("/api/recent/status")
    assert recent.status_code == 200


def test_predict_route_returns_model_prediction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.real_world as real_world

    data_dir = tmp_path / "real"
    data_dir.mkdir()
    _ieee_fixture().drop(columns=["fraud_probability"]).to_csv(data_dir / "train_transaction.csv", index=False)
    output = tmp_path / "model"
    run_pipeline(data_dir, output)
    monkeypatch.setattr(real_world, "MODEL_DIR", output)
    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/real/model/predict",
        json={
            "TransactionID": 1,
            "TransactionDT": 10_000,
            "TransactionAmt": 180.0,
            "ProductCD": "C",
            "card1": 1111,
            "card4": "visa",
            "C1": 4.0,
            "V1": 2.5,
            "isFraud": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provenance"] == PROVENANCE
    assert 0.0 <= body["fraud_risk_score"] <= 1.0
    assert "operating_threshold" in body
    assert body["not_a_live_production_decision"] is True
    assert "risk_level" not in body
    refused = client.post("/api/real/model/predict", json={"amount": 9.0, "v1": 0.1, "v2": 0.2})
    assert refused.status_code == 400
    incomplete = client.post("/api/real/model/predict", json={"TransactionAmt": 50.0})
    assert incomplete.status_code == 400
    assert incomplete.json()["incomplete_payload"] is True
    assert incomplete.json()["features_fabricated"] is False
    natural = client.post(
        "/api/real/model/predict",
        json={"TransactionAmt": 22.0, "ProductCD": "W", "TransactionDT": 10_200, "card1": 1112},
    )
    assert natural.status_code == 200
    assert natural.json()["incomplete_payload"] is False
    assert natural.json()["features_fabricated"] is False
    artifact = load_model(output / "ieee_hgb.joblib")
    scored = predict_transaction(
        artifact,
        {"TransactionAmt": 22.0, "ProductCD": "W", "TransactionDT": 10_200, "card1": 1112},
    )
    assert scored["provenance"] == PROVENANCE
