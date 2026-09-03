"""IEEE-CIS feature builder. isFraud is the target only; never a live feature."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from models.ieee_fraud import FORBIDDEN_FEATURES, TARGET_COLUMN

SECONDS_PER_HOUR = 3600
ID_COLUMN = "TransactionID"
ELAPSED_COLUMN = "TransactionDT"
AMOUNT_COLUMN = "TransactionAmt"
MAX_CATEGORIES = 255
ENCODER_VERSION = 1
HASH_MISSING_TOKEN = "__missing__"

NAMED_FEATURES = (
    "TransactionAmt",
    "TransactionDT",
    "ProductCD",
    "card1",
    "card2",
    "card3",
    "card4",
    "card5",
    "card6",
    "addr1",
    "addr2",
    "P_emaildomain",
    "R_emaildomain",
    "DeviceType",
    "DeviceInfo",
)

PREFIX_FEATURE = re.compile(r"^(C|D|M|V|id_)\d+")
CATEGORICAL_PREFIXES = ("M",)
CATEGORICAL_NAMED = frozenset(
    {
        "ProductCD",
        "card4",
        "card6",
        "P_emaildomain",
        "R_emaildomain",
        "DeviceType",
        "DeviceInfo",
    }
)


class FeatureLeakageError(ValueError):
    """A forbidden label or source-model column leaked into X."""


class PredictSchemaError(ValueError):
    """Payload is not an IEEE-CIS feature set this model can score honestly."""


def discover_feature_columns(header: list[str] | pd.Index) -> list[str]:
    present = list(header)
    selected: list[str] = []
    for name in present:
        if name in FORBIDDEN_FEATURES or name == ID_COLUMN:
            continue
        if name in NAMED_FEATURES or PREFIX_FEATURE.match(name):
            selected.append(name)
    return selected


def assert_no_leakage(frame: pd.DataFrame) -> None:
    leaked = [name for name in frame.columns if name in FORBIDDEN_FEATURES]
    if leaked:
        raise FeatureLeakageError(
            "Feature frame must not include labels or source-model outputs: "
            + ", ".join(sorted(leaked))
        )


def _series(frame: pd.DataFrame, name: str) -> pd.Series:
    if name in frame.columns:
        return frame[name]
    return pd.Series(pd.NA, index=frame.index)


def merge_identity(transactions: pd.DataFrame, identity: pd.DataFrame | None) -> pd.DataFrame:
    if identity is None or ID_COLUMN not in identity.columns:
        return transactions
    keep = [ID_COLUMN, *[name for name in identity.columns if name != ID_COLUMN]]
    devices = identity.loc[:, keep].drop_duplicates(subset=[ID_COLUMN])
    return transactions.merge(devices, on=ID_COLUMN, how="left")


def _is_categorical_column(name: str, series: pd.Series) -> bool:
    prefix = name[0] if name else ""
    if name.startswith("id_") and pd.api.types.is_numeric_dtype(series):
        return False
    return (
        name in CATEGORICAL_NAMED
        or (bool(PREFIX_FEATURE.match(name)) and prefix in CATEGORICAL_PREFIXES)
        or (name.startswith("id_") and not pd.api.types.is_numeric_dtype(series))
    )


def _hash_strings(raw: pd.Series) -> pd.Series:
    hashed = pd.util.hash_array(raw.fillna(HASH_MISSING_TOKEN).to_numpy())
    return pd.Series(hashed, index=raw.index, dtype="float64").where(raw.notna(), np.nan)


class CategoricalEncoder:
    """Train-only category maps. Unseen validation/test values become NaN."""

    def __init__(self) -> None:
        self.columns: list[str] = []
        self.kind: dict[str, str] = {}
        self.mappings: dict[str, dict[str, float]] = {}
        self.categorical_columns: list[str] = []
        self.hashed_columns: list[str] = []

    def fit(self, frame: pd.DataFrame) -> CategoricalEncoder:
        assert_no_leakage(frame)
        self.columns = list(frame.columns)
        self.kind = {}
        self.mappings = {}
        for name in self.columns:
            series = frame[name]
            if not _is_categorical_column(name, series):
                self.kind[name] = "numeric"
                continue
            raw = series.astype("string")
            nunique = int(raw.nunique(dropna=True))
            if nunique > MAX_CATEGORIES:
                self.kind[name] = "hashed"
                continue
            uniques = [str(value) for value in raw.dropna().unique().tolist()]
            self.kind[name] = "categorical"
            self.mappings[name] = {value: float(index) for index, value in enumerate(uniques)}
        self.categorical_columns = [name for name, kind in self.kind.items() if kind == "categorical"]
        self.hashed_columns = [name for name, kind in self.kind.items() if kind == "hashed"]
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not self.columns:
            raise ValueError("CategoricalEncoder must be fit on train before transform.")
        assert_no_leakage(frame)
        data: dict[str, pd.Series] = {}
        for name in self.columns:
            series = frame[name] if name in frame.columns else pd.Series(np.nan, index=frame.index)
            kind = self.kind[name]
            if kind == "numeric":
                data[name] = pd.to_numeric(series, errors="coerce")
                continue
            raw = series.astype("string")
            if kind == "hashed":
                data[name] = _hash_strings(raw)
                continue
            mapped = raw.map(self.mappings[name])
            data[name] = pd.to_numeric(mapped, errors="coerce")
        encoded = pd.DataFrame(data, index=frame.index)
        encoded.attrs["categorical"] = list(self.categorical_columns)
        return encoded

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": ENCODER_VERSION,
            "fitted_on": "train",
            "unseen_category_policy": "NaN",
            "max_categories": MAX_CATEGORIES,
            "columns": list(self.columns),
            "kind": dict(self.kind),
            "mappings": {name: dict(values) for name, values in self.mappings.items()},
            "categorical_columns": list(self.categorical_columns),
            "hashed_columns": list(self.hashed_columns),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CategoricalEncoder:
        encoder = cls()
        encoder.columns = list(payload["columns"])
        encoder.kind = {str(name): str(kind) for name, kind in payload["kind"].items()}
        encoder.mappings = {
            str(name): {str(key): float(code) for key, code in values.items()}
            for name, values in (payload.get("mappings") or {}).items()
        }
        encoder.categorical_columns = list(payload.get("categorical_columns") or [])
        encoder.hashed_columns = list(payload.get("hashed_columns") or [])
        return encoder


def build_feature_frame(
    transactions: pd.DataFrame,
    identity: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.Series | None, pd.DataFrame]:
    """Return raw X, optional y, and metadata. X is unencoded and never contains isFraud."""
    if ID_COLUMN not in transactions.columns:
        raise ValueError("IEEE-CIS feature builder requires TransactionID.")
    combined = merge_identity(transactions, identity)
    columns = discover_feature_columns(combined.columns)
    features = combined.loc[:, columns].copy()
    if ELAPSED_COLUMN in features.columns:
        elapsed = pd.to_numeric(features[ELAPSED_COLUMN], errors="coerce")
        features["relative_hour"] = (elapsed // SECONDS_PER_HOUR).astype("float64")
    assert_no_leakage(features)

    target = None
    if TARGET_COLUMN in combined.columns:
        target = pd.to_numeric(combined[TARGET_COLUMN], errors="coerce")

    meta = pd.DataFrame(
        {
            "transaction_id": combined[ID_COLUMN],
            "elapsed_seconds": pd.to_numeric(_series(combined, ELAPSED_COLUMN), errors="coerce"),
            "amount_usd": pd.to_numeric(_series(combined, AMOUNT_COLUMN), errors="coerce"),
        }
    )
    meta["relative_hour_bucket"] = (meta["elapsed_seconds"] // SECONDS_PER_HOUR).astype("Int64")
    if target is not None:
        meta["fraud_label"] = target
    return features, target, meta


def feature_spec(frame: pd.DataFrame, encoder: CategoricalEncoder | None = None) -> dict[str, Any]:
    if encoder is not None:
        columns = list(encoder.columns)
        categoricals = list(encoder.categorical_columns)
        hashed = list(encoder.hashed_columns)
    else:
        columns = list(frame.columns)
        categoricals = list(frame.attrs.get("categorical") or [])
        hashed = []
    return {
        "columns": columns,
        "categorical": categoricals,
        "hashed": hashed,
        "forbidden_excluded": sorted(FORBIDDEN_FEATURES),
        "target": TARGET_COLUMN,
        "target_in_features": TARGET_COLUMN in frame.columns,
        "preprocessing": {
            "fitted_on": "train",
            "unseen_category_policy": "NaN",
            "max_categories": MAX_CATEGORIES,
        },
    }
