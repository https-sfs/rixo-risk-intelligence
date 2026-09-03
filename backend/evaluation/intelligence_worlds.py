"""World-specific investigation intelligence. Uses existing evidence only."""

from __future__ import annotations

from typing import Any

from evaluation.intelligence import (
    BASELINE,
    BYOD_WORLD,
    DERIVED,
    EVALUATION,
    IEEE_WORLD,
    JANUARY_WORLD,
    OBSERVED,
    SYNTHETIC_WORLD,
    build_intelligence,
    custom_hourly_neighbors,
    entity_relationships,
    false_positive_impact,
    historical_baseline,
    ieee_hourly_neighbors,
    investigator_brief,
    january_hourly_neighbors,
    synthetic_hourly_neighbors,
    temporal_breakdown,
    _as_record,
    _int,
    _metric,
    _num,
)


def _labelled_value(block: Any) -> Any:
    record = _as_record(block)
    return record.get("value", block if not record else None)


def for_synthetic(evidence: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
    spike = _as_record(evidence.get("spike"))
    window = _as_record(evidence.get("window"))
    classifier = _as_record(evidence.get("classifier"))
    baseline_block = _as_record(evidence.get("baseline_comparison"))
    hourly = _as_record(baseline_block.get("hourly_baseline"))
    relationships = _as_record(evidence.get("relationships"))
    concentration = _as_record(evidence.get("concentration"))
    report = _as_record(report)
    recommended = _as_record(report.get("recommended_action"))
    case_id = str(spike.get("spike_id") or "")
    volume = _int(window.get("transaction_count") or spike.get("volume"))
    neighbors = synthetic_hourly_neighbors(str(spike.get("window_start") or ""))
    entities = entity_relationships(
        world=SYNTHETIC_WORLD,
        groups={
            "devices": [
                {
                    "id": item.get("entity_id"),
                    "count": item.get("transaction_count"),
                    "related": item.get("distinct_related"),
                    "provenance": OBSERVED,
                }
                for item in (relationships.get("device_to_accounts") or [])[:3]
            ],
            "subnets": [
                {
                    "id": item.get("entity_id"),
                    "count": item.get("transaction_count"),
                    "related": item.get("distinct_related"),
                    "provenance": OBSERVED,
                }
                for item in (relationships.get("subnet_to_accounts") or [])[:3]
            ],
            "skus": [
                {
                    "id": item.get("entity_id"),
                    "count": item.get("transaction_count"),
                    "share": item.get("share_of_transactions"),
                    "provenance": OBSERVED,
                }
                for item in (concentration.get("skus") or [])[:3]
            ],
        },
        missing=[],
    )
    current_volume = _num((hourly.get("window_volume")))
    baseline_volume = _as_record(hourly.get("baseline_volume")).get("value")
    ratio = _as_record(hourly.get("volume_change_ratio")).get("value")
    baseline = historical_baseline(
        current={"volume": current_volume, "label": "this hour"},
        baseline={"volume": baseline_volume, "ratio": ratio, "label": "hour-of-day baseline"},
        definition="Synthetic hour-of-day baseline from data/hourly_windows.csv on the seed-42 ledger.",
        provenance=BASELINE,
        unavailable=None
        if _as_record(hourly.get("baseline_volume")).get("status") == "available"
        else _as_record(hourly.get("baseline_volume")).get("reason") or "Hour-of-day baseline unavailable.",
    )
    reasons = list(spike.get("anomaly_reasons") or [])
    flagged = [f"Detector type: {spike.get('detector_type') or 'spike'}."]
    if reasons:
        flagged.append("Anomaly reasons: " + ", ".join(str(item) for item in reasons[:4]) + ".")
    if ratio is not None:
        flagged.append(f"Volume change versus hour-of-day baseline: {ratio}.")
    supports: list[str] = []
    if classifier.get("status") == "scored":
        supports.append(
            f"Classifier {classifier.get('classification')} at {classifier.get('fraud_risk_score')} "
            f"({classifier.get('high_risk_count')}/{classifier.get('scored_rows')} rows). Supporting evidence only."
        )
    else:
        supports.append("Classifier output is unavailable for this window.")
    next_checks = []
    if entities["groups"].get("devices"):
        next_checks.append("Review the top reused device and the accounts sharing it.")
    if entities["groups"].get("subnets"):
        next_checks.append("Check whether the dominant subnet is expected merchant traffic.")
    if str(recommended.get("type") or "") in {"monitor", "no_action"}:
        next_checks.append("Treat the High-risk classifier label as supporting context, not a fraud confirmation.")
    else:
        next_checks.append("Confirm the recommended scope against the concentrated entities before approval.")
    if not next_checks:
        next_checks.append("Compare this hour's diversity against the ordinary-hour baseline.")
    return build_intelligence(
        world=SYNTHETIC_WORLD,
        case_id=case_id,
        classifier=classifier,
        brief=investigator_brief(
            flagged=flagged,
            supports=supports,
            observed=[
                f"Window volume: {volume} transactions.",
                f"Unique accounts: {(_as_record(evidence.get('entities')).get('unique_accounts'))}.",
            ],
            derived=[
                f"Anomaly score: {spike.get('anomaly_score')}.",
                f"Coordination score: {spike.get('coordination_score')}.",
            ],
            uncertain=[
                "fraud_label in this window is delayed ground truth, not a live score.",
                "The IEEE-CIS classifier is transferred onto synthetic features.",
            ],
            next_checks=next_checks,
        ),
        temporal=temporal_breakdown(
            world=SYNTHETIC_WORLD,
            selected_label=str(spike.get("window_start") or ""),
            selected_count=volume,
            selected_amount=_num(window.get("total_amount")),
            selected_intensity=_num(spike.get("anomaly_score")),
            neighbors=neighbors,
            baseline_note="Neighbor hours come from the seed-42 hourly_windows artifact.",
            unavailable=None if neighbors else "Hourly windows artifact is unavailable.",
        ),
        entities=entities,
        baseline=baseline,
        case_metrics=[
            _metric(volume, provenance=OBSERVED, source="window.transaction_count")
            | {"label": "Transactions"},
            _metric(classifier.get("high_risk_count"), provenance="MODEL PREDICTION", source="classifier.high_risk_count")
            | {"label": "High-risk rows"},
            _metric(classifier.get("feature_coverage"), provenance="MODEL PREDICTION", source="classifier.feature_coverage")
            | {"label": "Feature coverage"},
            _metric(classifier.get("operating_threshold"), provenance="MODEL PREDICTION", source="operating_threshold")
            | {"label": "Operating threshold"},
        ],
        fp_impact=false_positive_impact(
            transaction_count=volume,
            high_risk_count=_int(classifier.get("high_risk_count")),
            recommended_action=str(recommended.get("type") or ""),
            labelled_fraud_count=_int(_as_record(window.get("fraud_label_rate")).get("labelled_count")),
        ),
    )


def for_january(anomaly: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    live = _as_record(evidence.get("live_evidence"))
    classifier = _as_record(evidence.get("classifier"))
    overlay = _as_record(evidence.get("evaluation_overlay"))
    hour = str(anomaly.get("hour_start") or evidence.get("hour_start") or "")
    txs = _int(_labelled_value(live.get("transaction_count")) or anomaly.get("transactions"))
    amount = _num(_labelled_value(live.get("amount_usd")) or anomaly.get("amount_usd"))
    neighbors = january_hourly_neighbors(hour)
    median = None
    if neighbors:
        counts = [row["transaction_count"] for row in neighbors if row.get("transaction_count") is not None]
        if counts:
            ordered = sorted(counts)
            median = ordered[len(ordered) // 2]
    signals = list(anomaly.get("signals") or evidence.get("signals") or [])
    entities = entity_relationships(
        world=JANUARY_WORLD,
        groups={},
        missing=["account", "device", "merchant", "SKU"],
    )
    baseline = historical_baseline(
        current={"volume": txs, "amount": amount, "label": hour},
        baseline={"volume": median, "label": "median of neighboring January hours"},
        definition="Neighboring hours from data/real_2026/hourly_metrics.csv. Not IEEE-CIS and not synthetic.",
        provenance=BASELINE,
        unavailable=None if neighbors else "January hourly_metrics.csv is unavailable.",
    )
    supports = (
        [
            f"Transferred classifier {classifier.get('classification')} at {classifier.get('fraud_risk_score')} "
            f"with feature coverage {classifier.get('feature_coverage')}. Not a January decision input."
        ]
        if classifier.get("status") == "scored"
        else ["Classifier output is unavailable or not scored."]
    )
    return build_intelligence(
        world=JANUARY_WORLD,
        case_id=str(anomaly.get("anomaly_id") or ""),
        classifier=classifier,
        brief=investigator_brief(
            flagged=[
                f"{anomaly.get('kind') or 'January anomaly'} at {hour}.",
                "Detection used hour-level volume and amount only.",
            ]
            + ([f"Signals: {', '.join(signals)}."] if signals else []),
            supports=supports,
            observed=[f"{txs} transactions.", f"Amount {amount} USD." if amount is not None else "Amount observed in the hour."],
            derived=["Hour bucket is floor(timestamp to hour).", "Neighbor comparison uses the January hourly artifact."],
            uncertain=[
                "is_fraud is delayed ground truth and was not a live input.",
                "Source CNN-LSTM outputs are excluded.",
                "Classifier coverage on January features is limited.",
            ],
            next_checks=[
                "Compare this hour's amount and volume with neighboring January hours.",
                "Do not treat the transferred High-risk label as fraud confirmed.",
            ],
        ),
        temporal=temporal_breakdown(
            world=JANUARY_WORLD,
            selected_label=hour,
            selected_count=txs,
            selected_amount=amount,
            selected_intensity=_num(anomaly.get("live_score")),
            neighbors=neighbors,
            baseline_note="Neighbor hours are January 2026 collection hours only.",
            unavailable=None if neighbors else "January hourly artifact is unavailable.",
        ),
        entities=entities,
        baseline=baseline,
        case_metrics=[
            _metric(txs, provenance=OBSERVED, source="live_evidence.transaction_count") | {"label": "Transactions"},
            _metric(amount, provenance=OBSERVED, source="live_evidence.amount_usd") | {"label": "Amount USD"},
            _metric(overlay.get("fraud_count"), provenance=EVALUATION, source="is_fraud overlay", status="evaluation_only")
            | {"label": "Labelled fraud"},
            _metric(classifier.get("feature_coverage"), provenance="MODEL PREDICTION", source="classifier.feature_coverage")
            | {"label": "Feature coverage"},
        ],
        fp_impact=false_positive_impact(
            transaction_count=txs,
            high_risk_count=_int(classifier.get("high_risk_count")),
            recommended_action="flag_for_human_review" if "amount" in " ".join(signals) else "review_time_window",
            labelled_fraud_count=_int(overlay.get("fraud_count")),
        ),
    )


def for_ieee(anomaly: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    live = _as_record(evidence.get("live_evidence"))
    classifier = _as_record(evidence.get("classifier") or evidence.get("model_prediction"))
    model = _as_record(evidence.get("model_prediction"))
    overlay = _as_record(evidence.get("evaluation_overlay"))
    product = _as_record(_labelled_value(live.get("product_concentration")))
    card = _as_record(_labelled_value(live.get("card_proxy_concentration")))
    hour = _int(anomaly.get("relative_hour_bucket") or evidence.get("relative_hour_bucket"))
    txs = _int(_labelled_value(live.get("transaction_count")) or anomaly.get("transactions"))
    amount = _num(_labelled_value(live.get("amount_usd")) or anomaly.get("amount_usd"))
    neighbors = ieee_hourly_neighbors(hour or 0) if hour is not None else []
    median = None
    if neighbors:
        counts = [row["transaction_count"] for row in neighbors if row.get("transaction_count") is not None]
        if counts:
            median = sorted(counts)[len(counts) // 2]
    groups: dict[str, list[dict[str, Any]]] = {}
    if product:
        groups["product"] = [
            {
                "id": product.get("value"),
                "count": product.get("count"),
                "share": product.get("share"),
                "provenance": DERIVED,
            }
        ]
    if card:
        groups["card_proxy"] = [
            {
                "id": card.get("value"),
                "count": card.get("count"),
                "share": card.get("share"),
                "provenance": "PROXY",
            }
        ]
    missing = ["IP/subnet", "true account identity", "SKU"]
    entities = entity_relationships(world=IEEE_WORLD, groups=groups, missing=missing)
    if groups:
        entities["note"] = "ProductCD share is derived. card4 is a proxy, not a true card identity."
    baseline = historical_baseline(
        current={"volume": txs, "amount": amount, "label": f"relative hour {hour}"},
        baseline={"volume": median, "label": "median of neighboring relative hours"},
        definition="Neighboring relative-hour buckets from data/real/hourly_metrics.csv. Elapsed time, not calendar dates.",
        provenance=BASELINE,
        unavailable=None if neighbors else "IEEE hourly_metrics.csv is unavailable.",
    )
    scope = str(model.get("sample_scope") or classifier.get("sample_scope") or "")
    supports = []
    if classifier.get("status") == "scored" or model:
        supports.append(
            f"Classifier overlay p95 {model.get('p95_score') or classifier.get('fraud_risk_score')}; "
            f"{model.get('high_risk_count') or classifier.get('high_risk_count')} rows at threshold "
            f"{model.get('threshold') or classifier.get('operating_threshold')}."
        )
        if scope == "IN_SAMPLE_MODEL_OVERLAY":
            supports.append("This hour is IN_SAMPLE_MODEL_OVERLAY — not held-out test performance.")
    signals = list(anomaly.get("signals") or [])
    return build_intelligence(
        world=IEEE_WORLD,
        case_id=str(anomaly.get("anomaly_id") or ""),
        classifier={**classifier, "sample_scope": scope or classifier.get("sample_scope")},
        sample_scope=scope or None,
        brief=investigator_brief(
            flagged=[
                f"Relative hour {hour} is a live IEEE-CIS hour-level anomaly.",
                f"Signals: {', '.join(signals) or 'hour-level detector'}.",
            ],
            supports=supports or ["No classifier overlay is attached to this hour."],
            observed=[f"{txs} transactions.", f"Amount {amount} USD." if amount is not None else "Amount observed."],
            derived=[
                "Relative hour is elapsed TransactionDT, not a calendar date.",
                f"Top ProductCD share: {product.get('share')}." if product else "ProductCD share unavailable.",
            ],
            uncertain=[
                "isFraud is delayed ground truth and was not a live detector input.",
                "Hour-detector holdout precision/recall are not classifier test metrics.",
                "True account, device, and network identities are unavailable.",
            ],
            next_checks=[
                "Compare this relative hour with neighboring hours on volume and ProductCD share.",
                "Treat overlay scores as supporting evidence, not test-set accuracy.",
            ],
        ),
        temporal=temporal_breakdown(
            world=IEEE_WORLD,
            selected_label=f"relative hour {hour}",
            selected_count=txs,
            selected_amount=amount,
            selected_intensity=_num(anomaly.get("live_score")),
            neighbors=neighbors,
            baseline_note="Relative hours are elapsed-time buckets. In-sample overlay hours are not test metrics.",
            unavailable=None if neighbors else "IEEE hourly artifact is unavailable.",
        ),
        entities=entities,
        baseline=baseline,
        case_metrics=[
            _metric(txs, provenance=OBSERVED, source="hour row count") | {"label": "Transactions"},
            _metric(amount, provenance=OBSERVED, source="TransactionAmt") | {"label": "Amount USD"},
            _metric(model.get("high_risk_count"), provenance="MODEL PREDICTION", source="hour overlay")
            | {"label": "High-risk rows"},
            _metric(overlay.get("fraud_count"), provenance=EVALUATION, source="isFraud overlay", status="evaluation_only")
            | {"label": "Labelled fraud"},
        ],
        fp_impact=false_positive_impact(
            transaction_count=txs,
            high_risk_count=_int(model.get("high_risk_count") or classifier.get("high_risk_count")),
            recommended_action="flag_high_risk_transactions"
            if _int(model.get("high_risk_count") or 0)
            else "review_hour",
            labelled_fraud_count=_int(overlay.get("fraud_count")),
        ),
    )


def for_custom(
    anomaly: dict[str, Any],
    evidence: dict[str, Any],
    hourly: list[dict[str, Any]] | None = None,
    mapped_roles: list[str] | None = None,
) -> dict[str, Any]:
    live = _as_record(evidence.get("live_evidence"))
    classifier = _as_record(evidence.get("classifier"))
    overlay = _as_record(evidence.get("evaluation_overlay"))
    hour = str(anomaly.get("hour_start") or evidence.get("hour_start") or "")
    txs = _int(_labelled_value(live.get("transaction_count")) or anomaly.get("transactions"))
    amount = _num(_labelled_value(live.get("amount") or live.get("amount_usd")) or anomaly.get("amount"))
    neighbors = custom_hourly_neighbors(hourly, hour)
    roles = mapped_roles or []
    groups: dict[str, list[dict[str, Any]]] = {}
    missing: list[str] = []
    for role in ("account_id", "device_id", "merchant", "product_sku"):
        packed = _as_record(live.get(f"{role}_top") or live.get(role))
        if packed.get("value") or packed.get("id"):
            groups[role] = [
                {
                    "id": packed.get("value") or packed.get("id"),
                    "count": packed.get("count"),
                    "share": packed.get("share"),
                    "provenance": packed.get("label") or packed.get("provenance") or OBSERVED,
                }
            ]
        elif role not in roles:
            missing.append(role)
    entities = entity_relationships(world=BYOD_WORLD, groups=groups, missing=missing)
    median = None
    if neighbors:
        counts = [row["transaction_count"] for row in neighbors if row.get("transaction_count") is not None]
        if counts:
            median = sorted(counts)[len(counts) // 2]
    baseline = historical_baseline(
        current={"volume": txs, "amount": amount, "label": hour},
        baseline={"volume": median, "label": "median of neighboring uploaded hours"},
        definition="User-dataset hourly history collected during analyze. Not compared with Synthetic, IEEE-CIS, or January.",
        provenance=BASELINE,
        unavailable=None if neighbors else "User-dataset hourly history was not retained for this session.",
    )
    supports = (
        [
            f"Classifier {classifier.get('classification')} at {classifier.get('fraud_risk_score')} "
            f"with coverage {classifier.get('feature_coverage')}."
        ]
        if classifier.get("status") == "scored"
        else ["Classifier output is unavailable because required features were not mapped."]
    )
    if overlay.get("label"):
        supports.append(f"{overlay.get('label')} is evaluation only and is not a model feature.")
    return build_intelligence(
        world=BYOD_WORLD,
        case_id=str(anomaly.get("anomaly_id") or ""),
        classifier=classifier,
        brief=investigator_brief(
            flagged=[
                f"{anomaly.get('kind') or 'User-dataset anomaly'} at {hour}.",
                f"Signals: {', '.join(anomaly.get('signals') or []) or 'mapped live fields only'}.",
            ],
            supports=supports,
            observed=[f"{txs} transactions."] + ([f"Amount {amount}."] if amount is not None else []),
            derived=["Time window is floor(mapped timestamp) unless a relative elapsed field was mapped."],
            uncertain=[
                "Only mapped user fields were used.",
                "Missing IEEE features were not fabricated.",
            ]
            + ([f"Unmapped for clustering: {', '.join(missing)}."] if missing else []),
            next_checks=[
                "Review only entities that were actually mapped.",
                "Do not treat user-provided labels as the system's fraud decision.",
            ],
        ),
        temporal=temporal_breakdown(
            world=BYOD_WORLD,
            selected_label=hour,
            selected_count=txs,
            selected_amount=amount,
            selected_intensity=_num(anomaly.get("live_score")),
            neighbors=neighbors,
            baseline_note="Neighbor hours are from this upload only.",
            unavailable=None if neighbors else "Hourly history for this upload is unavailable.",
        ),
        entities=entities,
        baseline=baseline,
        case_metrics=[
            _metric(txs, provenance=OBSERVED, source="mapped window row count") | {"label": "Transactions"},
            _metric(amount, provenance=OBSERVED, source="mapped amount") | {"label": "Amount"},
            _metric(overlay.get("fraud_count"), provenance=EVALUATION, source="USER-PROVIDED GROUND TRUTH", status="evaluation_only")
            | {"label": "User labels"},
            _metric(classifier.get("feature_coverage"), provenance="MODEL PREDICTION", source="classifier.feature_coverage")
            | {"label": "Feature coverage"},
        ],
        fp_impact=false_positive_impact(
            transaction_count=txs,
            high_risk_count=_int(classifier.get("high_risk_count")),
            recommended_action="flag_for_human_review",
            labelled_fraud_count=_int(overlay.get("fraud_count")),
        ),
    )
