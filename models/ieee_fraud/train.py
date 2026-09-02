"""Fit HistGradientBoostingClassifier on IEEE-CIS features only."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.utils.class_weight import compute_sample_weight

from models.ieee_fraud.features import assert_no_leakage

MAX_ITER = 80
LEARNING_RATE = 0.08
MAX_DEPTH = 7
MIN_SAMPLES_LEAF = 80
RANDOM_STATE = 42


def fit_classifier(features: pd.DataFrame, target: pd.Series) -> HistGradientBoostingClassifier:
    assert_no_leakage(features)
    y = pd.to_numeric(target, errors="coerce")
    valid = y.notna()
    X = features.loc[valid]
    y = y.loc[valid].astype(int)
    weights = compute_sample_weight("balanced", y)
    min_leaf = min(MIN_SAMPLES_LEAF, max(2, int(len(X) / 20)))
    categorical = [name for name in (X.attrs.get("categorical") or []) if name in X.columns]
    model = HistGradientBoostingClassifier(
        max_iter=MAX_ITER,
        learning_rate=LEARNING_RATE,
        max_depth=MAX_DEPTH,
        min_samples_leaf=min_leaf,
        categorical_features=categorical or None,
        random_state=RANDOM_STATE,
    )
    model.fit(X, y, sample_weight=weights)
    return model
