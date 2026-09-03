"""Transparent rolling-baseline and z-score helpers for spike scoring."""

from __future__ import annotations

import numpy as np
import pandas as pd

ROLLING_WINDOWS = 72
MIN_BASELINE_PERIODS = 24
HOUR_OF_DAY_LOOKBACK_DAYS = 10
MIN_HOUR_BASELINE_PERIODS = 4
Z_FLOOR = 0.35

SPIKE_TYPE_ORDINARY = "ordinary"
SPIKE_TYPE_FESTIVE = "legitimate_festive_spike"
SPIKE_TYPE_COORDINATED = "suspicious_coordinated_spike"

VOLUME_Z_FESTIVE = 2.0
COORDINATION_SUSPICIOUS = 3.4
COORDINATION_FESTIVE_MAX = 2.2
MIN_SPIKE_VOLUME = 16
CONCENTRATED_SUBNET_LIMIT = 6


def _finite(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if pd.isna(number):
        return default
    return number


def rolling_baseline(series: pd.Series, windows: int = ROLLING_WINDOWS) -> tuple[pd.Series, pd.Series]:
    shifted = series.shift(1)
    mean = shifted.rolling(windows, min_periods=MIN_BASELINE_PERIODS).mean()
    std = shifted.rolling(windows, min_periods=MIN_BASELINE_PERIODS).std()
    return mean, std


def z_score(value: pd.Series, mean: pd.Series, std: pd.Series) -> pd.Series:
    safe_std = std.clip(lower=Z_FLOOR)
    return (value - mean) / safe_std


def hour_of_day_baseline(windows: pd.DataFrame, column: str) -> tuple[pd.Series, pd.Series]:
    """Compare this clock hour to the same clock hour on recent prior days.

    A short rolling mean would absorb a multi-day sale and hide a festive lift.
    """
    starts = pd.to_datetime(windows["window_start"])
    values = windows[column].to_numpy()
    means: list[float] = []
    stds: list[float] = []
    for index, start in enumerate(starts):
        low = start - pd.Timedelta(days=HOUR_OF_DAY_LOOKBACK_DAYS)
        hist = [
            values[j]
            for j, other in enumerate(starts)
            if j < index and low <= other < start and other.hour == start.hour
        ]
        if len(hist) < MIN_HOUR_BASELINE_PERIODS:
            means.append(float("nan"))
            stds.append(float("nan"))
            continue
        means.append(float(np.mean(hist)))
        means_std = float(np.std(hist, ddof=1)) if len(hist) > 1 else Z_FLOOR
        stds.append(means_std)
    return pd.Series(means, index=windows.index), pd.Series(stds, index=windows.index)


def add_baselines(windows: pd.DataFrame) -> pd.DataFrame:
    scored = windows.copy()
    volume_mean, volume_std = hour_of_day_baseline(scored, "volume")
    scored["baseline_volume"] = volume_mean
    scored["z_volume"] = z_score(scored["volume"], volume_mean, volume_std)

    for column in (
        "fraud_rate",
        "failure_rate",
        "accounts_per_device",
        "txs_per_device",
        "txs_per_subnet",
        "top_sku_share",
        "pincode_concentration",
        "mean_device_velocity",
    ):
        mean, std = rolling_baseline(scored[column])
        scored[f"baseline_{column}"] = mean
        scored[f"z_{column}"] = z_score(scored[column], mean, std)
    return scored


def coordination_score(row: pd.Series) -> tuple[float, list[str]]:
    """Score coordination/abuse structure. Volume is intentionally excluded."""
    reasons: list[str] = []
    score = 0.0

    def _add(weight: float, z_value: float, reason: str, threshold: float = 1.6) -> float:
        contribution = weight * max(float(z_value), 0.0)
        if z_value >= threshold:
            reasons.append(reason)
        return contribution

    score += _add(1.1, _finite(row.get("z_failure_rate")), "failure_rate_above_baseline")
    score += _add(0.9, _finite(row.get("z_accounts_per_device")), "many_accounts_per_device")
    score += _add(1.0, _finite(row.get("z_txs_per_device")), "high_device_reuse")
    if int(row["unique_ip_subnets"]) <= CONCENTRATED_SUBNET_LIMIT:
        score += _add(1.0, _finite(row.get("z_txs_per_subnet")), "ip_subnet_concentration")
    score += _add(0.9, _finite(row.get("z_top_sku_share")), "sku_concentration")
    score += _add(0.8, _finite(row.get("z_pincode_concentration")), "pincode_concentration")
    score += _add(0.8, _finite(row.get("z_mean_device_velocity")), "elevated_device_velocity")

    if float(row["failure_rate"]) >= 0.32 and int(row["volume"]) >= MIN_SPIKE_VOLUME:
        score += 1.2
        if "high_absolute_failure_rate" not in reasons:
            reasons.append("high_absolute_failure_rate")
    if float(row["accounts_per_device"]) >= 4.0 and int(row["volume"]) >= MIN_SPIKE_VOLUME:
        score += 1.4
        reasons.append("shared_device_cluster")
    if float(row["top_sku_share"]) >= 0.55 and int(row["volume"]) >= MIN_SPIKE_VOLUME:
        score += 0.8
        reasons.append("narrow_sku_targeting")
    if int(row["unique_ip_subnets"]) <= 2 and int(row["volume"]) >= MIN_SPIKE_VOLUME:
        score += 1.1
        reasons.append("few_ip_subnets_for_volume")

    return score, reasons


def classify_window(row: pd.Series, coord_score: float, reasons: list[str]) -> tuple[str, str, float, list[str]]:
    volume = int(row["volume"])
    volume_z = _finite(row.get("z_volume"))
    baseline_volume = _finite(row.get("baseline_volume"), default=float("nan"))
    volume_ratio = volume / baseline_volume if baseline_volume and baseline_volume > 0 else np.nan
    anomaly_score = coord_score + 0.35 * max(volume_z, 0.0)
    missing_volume_baseline = pd.isna(row.get("baseline_volume"))
    diverse_structure = (
        float(row["accounts_per_device"]) < 2.0
        and float(row["top_sku_share"]) < 0.28
        and int(row["unique_pincodes"]) >= 8
        and int(row["unique_ip_subnets"]) >= 8
        and float(row["failure_rate"]) < 0.22
    )

    if volume < MIN_SPIKE_VOLUME:
        return SPIKE_TYPE_ORDINARY, "none", anomaly_score, reasons

    if coord_score >= COORDINATION_SUSPICIOUS and not diverse_structure:
        if anomaly_score >= 8.5:
            severity = "high"
        elif anomaly_score >= 5.5:
            severity = "medium"
        else:
            severity = "low"
        if volume_z >= 1.2:
            reasons = ["volume_above_baseline", *reasons]
        return SPIKE_TYPE_COORDINATED, severity, anomaly_score, reasons

    if missing_volume_baseline:
        return SPIKE_TYPE_ORDINARY, "none", anomaly_score, reasons

    festive_like = (
        volume_z >= VOLUME_Z_FESTIVE
        and coord_score < COORDINATION_FESTIVE_MAX
        and float(row["failure_rate"]) < 0.22
        and float(row["accounts_per_device"]) < 2.4
        and float(row["top_sku_share"]) < 0.28
        and int(row["unique_pincodes"]) >= 8
        and int(row["unique_ip_subnets"]) >= 6
    )
    if festive_like:
        reasons = ["high_volume_with_preserved_diversity", *reasons]
        return SPIKE_TYPE_FESTIVE, "info", anomaly_score, reasons

    if volume_z >= VOLUME_Z_FESTIVE and not pd.isna(volume_ratio) and volume_ratio >= 2.0:
        reasons = ["volume_increase_without_coordination", *reasons]
        return SPIKE_TYPE_FESTIVE, "info", anomaly_score, reasons

    return SPIKE_TYPE_ORDINARY, "none", anomaly_score, reasons
