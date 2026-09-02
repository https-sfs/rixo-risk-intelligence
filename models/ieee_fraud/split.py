"""Chronological 70/10/20 split on TransactionDT. No random shuffle."""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.ieee_fraud import TRAIN_FRACTION, VALIDATION_FRACTION


def temporal_masks(
    elapsed: pd.Series,
    train_fraction: float = TRAIN_FRACTION,
    validation_fraction: float = VALIDATION_FRACTION,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1.")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1.")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train_fraction + validation_fraction must leave a test remainder.")
    values = pd.to_numeric(elapsed, errors="coerce")
    if values.isna().all():
        raise ValueError("Temporal split requires TransactionDT / elapsed seconds.")
    train_cutoff = float(values.quantile(train_fraction))
    valid_cutoff = float(values.quantile(train_fraction + validation_fraction))
    train = (values <= train_cutoff).to_numpy()
    valid = ((values > train_cutoff) & (values <= valid_cutoff)).to_numpy()
    test = (values > valid_cutoff).to_numpy()
    if not train.any() or not valid.any() or not test.any():
        raise ValueError("Temporal 70/10/20 split produced an empty side. Check TransactionDT coverage.")
    if (train & valid).any() or (train & test).any() or (valid & test).any():
        raise ValueError("Temporal split leaked: a row is in more than one fold.")
    train_max = float(values[train].max())
    valid_min = float(values[valid].min())
    valid_max = float(values[valid].max())
    test_min = float(values[test].min())
    if train_max > valid_min:
        raise ValueError("Temporal split leaked: train elapsed exceeds validation minimum.")
    if valid_max > test_min:
        raise ValueError("Temporal split leaked: validation elapsed exceeds test minimum.")
    return train, valid, test


def split_stats(target: pd.Series, meta: pd.DataFrame) -> dict[str, float | int | None]:
    labels = pd.to_numeric(target, errors="coerce")
    elapsed = pd.to_numeric(meta["elapsed_seconds"], errors="coerce")
    return {
        "rows": int(len(labels)),
        "fraud": int((labels == 1).sum()),
        "prevalence": float(labels.mean()) if len(labels) else None,
        "elapsed_min": float(elapsed.min()) if elapsed.notna().any() else None,
        "elapsed_max": float(elapsed.max()) if elapsed.notna().any() else None,
    }


def split_frames(
    features: pd.DataFrame,
    target: pd.Series,
    meta: pd.DataFrame,
    train_fraction: float = TRAIN_FRACTION,
    validation_fraction: float = VALIDATION_FRACTION,
) -> dict[str, pd.DataFrame | pd.Series | np.ndarray | float]:
    train_mask, valid_mask, test_mask = temporal_masks(
        meta["elapsed_seconds"],
        train_fraction=train_fraction,
        validation_fraction=validation_fraction,
    )
    return {
        "X_train": features.loc[train_mask].copy(),
        "X_valid": features.loc[valid_mask].copy(),
        "X_test": features.loc[test_mask].copy(),
        "y_train": target.loc[train_mask],
        "y_valid": target.loc[valid_mask],
        "y_test": target.loc[test_mask],
        "meta_train": meta.loc[train_mask],
        "meta_valid": meta.loc[valid_mask],
        "meta_test": meta.loc[test_mask],
        "train_mask": train_mask,
        "valid_mask": valid_mask,
        "test_mask": test_mask,
        "train_cutoff_elapsed": float(pd.to_numeric(meta.loc[train_mask, "elapsed_seconds"]).max()),
        "valid_cutoff_elapsed": float(pd.to_numeric(meta.loc[valid_mask, "elapsed_seconds"]).max()),
        "train_fraction": train_fraction,
        "validation_fraction": validation_fraction,
        "test_fraction": round(1.0 - train_fraction - validation_fraction, 6),
    }
