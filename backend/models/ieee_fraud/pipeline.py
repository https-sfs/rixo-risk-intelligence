"""Train, evaluate, and write IEEE-CIS model artifacts. Does not touch seed-42 paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.real_data.mapper import (
    assert_not_synthetic_world_path,
    identity_file,
    missing_dataset_message,
    transaction_file,
)
from models.ieee_fraud import (
    ENCODER_NAME,
    EVALUATION_NAME,
    FEATURE_SPEC_NAME,
    FORBIDDEN_FEATURES,
    JOBLIB_NAME,
    MODEL_DIR,
    OVERLAY_NAME,
    WORLD,
)
from models.ieee_fraud.evaluate import compose_evaluation, evaluate_scores
from models.ieee_fraud.features import CategoricalEncoder, build_feature_frame, feature_spec
from models.ieee_fraud.overlay import aggregate_hour_scores
from models.ieee_fraud.predict import IeeeFraudArtifact, save_encoder, save_model, score_encoded
from models.ieee_fraud.split import split_frames, split_stats
from models.ieee_fraud.train import fit_classifier


def _load_ieee(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    tx_path = transaction_file(data_dir)
    if not tx_path.is_file():
        from evaluation.real_data.mapper import MissingRealDatasetError

        raise MissingRealDatasetError(missing_dataset_message(data_dir))
    transactions = pd.read_csv(tx_path)
    leaked = [name for name in FORBIDDEN_FEATURES if name in transactions.columns and name != "isFraud"]
    if leaked:
        transactions = transactions.drop(columns=leaked, errors="ignore")
    identity = None
    ident_path = identity_file(data_dir)
    if ident_path.is_file():
        identity = pd.read_csv(ident_path)
    return transactions, identity


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    assert_not_synthetic_world_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _encode_split(
    encoder: CategoricalEncoder,
    split: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    x_train = encoder.transform(split["X_train"])
    x_valid = encoder.transform(split["X_valid"])
    x_test = encoder.transform(split["X_test"])
    return x_train, x_valid, x_test


def run_pipeline(
    data_dir: Path,
    output_dir: Path | None = None,
    anomalies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    dest = Path(output_dir) if output_dir is not None else MODEL_DIR
    assert_not_synthetic_world_path(dest / EVALUATION_NAME)
    transactions, identity = _load_ieee(Path(data_dir))
    raw_features, target, meta = build_feature_frame(transactions, identity)
    if target is None:
        raise ValueError("IEEE-CIS training requires isFraud as the target column.")
    split = split_frames(raw_features, target, meta)
    encoder = CategoricalEncoder().fit(split["X_train"])
    x_train, x_valid, x_test = _encode_split(encoder, split)
    model = fit_classifier(x_train, split["y_train"])
    validation = evaluate_scores(split["y_valid"].to_numpy(), score_encoded(model, x_valid))
    frozen_threshold = float(validation["threshold"])
    test = evaluate_scores(
        split["y_test"].to_numpy(),
        score_encoded(model, x_test),
        threshold=frozen_threshold,
    )
    spec = feature_spec(raw_features, encoder)
    split_payload = {
        "kind": "temporal_chronological",
        "train_fraction": split["train_fraction"],
        "validation_fraction": split["validation_fraction"],
        "test_fraction": split["test_fraction"],
        "shuffled": False,
        "train_cutoff_elapsed_seconds": split["train_cutoff_elapsed"],
        "valid_cutoff_elapsed_seconds": split["valid_cutoff_elapsed"],
        "train": split_stats(split["y_train"], split["meta_train"]),
        "validation": split_stats(split["y_valid"], split["meta_valid"]),
        "test": split_stats(split["y_test"], split["meta_test"]),
    }
    preprocessing = {
        **encoder.to_dict(),
        "mappings": {name: len(values) for name, values in encoder.mappings.items()},
        "note": "Full category-to-code maps live in encoder.json and ieee_hgb.joblib.",
    }
    evaluation = compose_evaluation(
        validation=validation,
        test=test,
        split=split_payload,
        feature_spec_payload=spec,
        preprocessing=preprocessing,
        estimator={
            "type": "sklearn.ensemble.HistGradientBoostingClassifier",
            "sample_weight": "balanced",
            "sample_weight_fitted_on": "train labels only",
            "not_an_llm": True,
            "not_the_january_2026_source_model": True,
        },
    )

    artifact = IeeeFraudArtifact(
        estimator=model,
        encoder=encoder,
        threshold=frozen_threshold,
        metadata={
            "feature_spec": spec,
            "split": {
                "kind": split_payload["kind"],
                "train_cutoff_elapsed_seconds": split_payload["train_cutoff_elapsed_seconds"],
                "valid_cutoff_elapsed_seconds": split_payload["valid_cutoff_elapsed_seconds"],
            },
        },
    )

    overlay_raw = raw_features
    overlay_meta = meta
    if anomalies:
        buckets = {int(item["relative_hour_bucket"]) for item in anomalies if "relative_hour_bucket" in item}
        mask = meta["relative_hour_bucket"].isin(buckets)
        overlay_raw = raw_features.loc[mask].copy()
        overlay_meta = meta.loc[mask]
    scored = overlay_meta.copy()
    scored["fraud_risk_score"] = artifact.score(overlay_raw) if len(overlay_raw) else []
    overlay = aggregate_hour_scores(
        scored,
        threshold=frozen_threshold,
        train_cutoff_elapsed=float(split["train_cutoff_elapsed"]),
    )

    _write_json(dest / FEATURE_SPEC_NAME, spec)
    _write_json(dest / EVALUATION_NAME, evaluation)
    _write_json(dest / OVERLAY_NAME, overlay)
    save_encoder(encoder, dest / ENCODER_NAME)
    save_model(artifact, dest / JOBLIB_NAME)
    return {
        "world": WORLD,
        "output_dir": str(dest),
        "validation_f1": validation["f1"],
        "test_pr_auc": test["ranking"]["pr_auc"],
        "test_roc_auc": test["ranking"]["roc_auc"],
        "operating_threshold": frozen_threshold,
        "threshold_source": "validation",
        "overlay_hours": len(overlay["hours"]),
        "artifacts": [JOBLIB_NAME, ENCODER_NAME, FEATURE_SPEC_NAME, EVALUATION_NAME, OVERLAY_NAME],
    }


if __name__ == "__main__":
    repo = Path(__file__).resolve().parent.parent.parent
    real_dir = repo / "data" / "real"
    anomalies_path = real_dir / "anomalies.json"
    anomaly_list = None
    if anomalies_path.is_file():
        anomaly_list = json.loads(anomalies_path.read_text(encoding="utf-8")).get("anomalies")
    print(json.dumps(run_pipeline(real_dir, MODEL_DIR, anomalies=anomaly_list), indent=2))
