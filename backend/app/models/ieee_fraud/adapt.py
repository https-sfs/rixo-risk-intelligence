"""World-specific adapters into the canonical IEEE-CIS classifier contract.

Adapters only derive features that the existing classifier actually consumes.
Unavailable fields stay absent. January v1–v28 are never mapped onto V*.
Labels and source-model outputs are never features.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from models.ieee_fraud import FORBIDDEN_FEATURES
from models.ieee_fraud.features import ID_COLUMN, discover_feature_columns
from models.ieee_fraud.infer import REQUIRED_CANONICAL, expected_feature_columns
from models.ieee_fraud.predict import RECENT_PCA

IEEE_PRODUCT_CODES = frozenset({"W", "C", "H", "R", "S"})
UNAVAILABLE_FAMILIES = (
    "ProductCD",
    "card2-card6",
    "addr*",
    "email domains",
    "DeviceType",
    "C*",
    "D*",
    "M*",
    "V*",
    "id_*",
)


@dataclass
class Adaptation:
    frame: pd.DataFrame
    world: str
    features_used: list[str] = field(default_factory=list)
    features_derived: list[str] = field(default_factory=list)
    features_native: list[str] = field(default_factory=list)
    features_unavailable: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def can_score(self) -> bool:
        return not self.missing_required and not self.frame.empty


def _hash_to_card1(series: pd.Series) -> pd.Series:
    raw = series.astype("string")
    hashed = pd.util.hash_array(raw.fillna("__missing__").to_numpy())
    values = (hashed.astype("uint64") % 16000 + 1000).astype("float64")
    return pd.Series(values, index=series.index).where(raw.notna(), np.nan)


def _as_elapsed(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        origin = series.min()
        if pd.isna(origin):
            return pd.Series(np.nan, index=series.index)
        return (series - origin).dt.total_seconds()
    numeric = pd.to_numeric(series, errors="coerce")
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.notna().sum() > 0 and parsed.notna().sum() >= numeric.notna().sum():
        origin = parsed.min()
        if pd.isna(origin):
            return numeric
        return (parsed - origin).dt.total_seconds()
    return numeric


def _product_cd(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip().str.upper()
    return text.where(text.isin(IEEE_PRODUCT_CODES), pd.NA)


def _counts(keys: pd.Series) -> pd.Series:
    valid = keys.astype("string")
    mapped = valid.groupby(valid, dropna=True).transform("size")
    return pd.to_numeric(mapped, errors="coerce")


def _hourly_counts(keys: pd.Series, elapsed: pd.Series) -> pd.Series:
    hours = (pd.to_numeric(elapsed, errors="coerce") // 3600).astype("Int64")
    ident = keys.astype("string")
    combo = ident.astype("string") + "|" + hours.astype("string")
    return _counts(combo).where(ident.notna() & hours.notna(), np.nan)


def _finalize(world: str, frame: pd.DataFrame, derived: list[str], notes: list[str]) -> Adaptation:
    leaked = [name for name in frame.columns if name in FORBIDDEN_FEATURES or name in {"is_fraud", "fraud_label"}]
    if leaked:
        frame = frame.drop(columns=leaked)
    used = [name for name in frame.columns if name != ID_COLUMN and frame[name].notna().any()]
    expected = expected_feature_columns()
    unavailable = [name for name in expected if name not in used]
    missing = [name for name in REQUIRED_CANONICAL if name not in used]
    native = [name for name in used if name not in derived]
    families = [name for name in UNAVAILABLE_FAMILIES if any(u.startswith(name[:1]) or name in u for u in unavailable)]
    return Adaptation(
        frame=frame,
        world=world,
        features_used=used,
        features_derived=list(dict.fromkeys(derived)),
        features_native=native,
        features_unavailable=unavailable if len(unavailable) <= 40 else families or unavailable[:20],
        missing_required=missing,
        notes=notes,
    )


def adapt_ieee(frame: pd.DataFrame, *, world: str = "REAL PUBLIC DATA") -> Adaptation:
    official = [name for name in discover_feature_columns(frame.columns) if not RECENT_PCA.fullmatch(str(name))]
    work = frame.loc[:, [name for name in official if name in frame.columns]].copy()
    if ID_COLUMN in frame.columns:
        work[ID_COLUMN] = frame[ID_COLUMN]
    elif "transaction_id" in frame.columns:
        work[ID_COLUMN] = frame["transaction_id"]
    notes = ["Native IEEE-CIS columns passed through. Missing IEEE fields stay missing."]
    return _finalize(world, work, derived=[], notes=notes)


def adapt_recent(mapped: pd.DataFrame, *, world: str = "RECENT PUBLIC DATA") -> Adaptation:
    work = pd.DataFrame(index=mapped.index)
    derived: list[str] = []
    notes = [
        "January amount and timestamp are derived into TransactionAmt and TransactionDT.",
        "v1–v28 are source PCA features and are not IEEE-CIS V*.",
    ]
    amount = None
    if "amount_usd" in mapped.columns:
        amount = pd.to_numeric(mapped["amount_usd"], errors="coerce")
    elif "amount" in mapped.columns:
        amount = pd.to_numeric(mapped["amount"], errors="coerce")
    if amount is not None:
        work["TransactionAmt"] = amount
        derived.append("TransactionAmt")
    time_col = None
    for name in ("event_timestamp", "timestamp"):
        if name in mapped.columns:
            time_col = mapped[name]
            break
    if time_col is not None:
        work["TransactionDT"] = _as_elapsed(time_col)
        derived.append("TransactionDT")
    if "transaction_id" in mapped.columns:
        work[ID_COLUMN] = mapped["transaction_id"]
    return _finalize(world, work, derived=derived, notes=notes)


def adapt_custom(
    mapped: pd.DataFrame,
    *,
    world: str = "BRING YOUR DATA",
) -> Adaptation:
    """Map user columns (canonical roles and any official IEEE names) into the contract."""
    data: dict[str, pd.Series] = {}
    derived: list[str] = []
    notes: list[str] = []
    official = [
        name
        for name in discover_feature_columns(mapped.columns)
        if not RECENT_PCA.fullmatch(str(name))
    ]
    for name in official:
        data[name] = mapped[name]
    if ID_COLUMN not in data:
        if "transaction_id" in mapped.columns:
            data[ID_COLUMN] = mapped["transaction_id"]
        elif "TransactionID" in mapped.columns:
            data[ID_COLUMN] = mapped["TransactionID"]

    if "TransactionAmt" not in data or data["TransactionAmt"].isna().all():
        if "amount" in mapped.columns:
            data["TransactionAmt"] = pd.to_numeric(mapped["amount"], errors="coerce")
            derived.append("TransactionAmt")
            notes.append("TransactionAmt derived from the mapped amount column.")

    if "TransactionDT" not in data or data["TransactionDT"].isna().all():
        if "timestamp" in mapped.columns:
            data["TransactionDT"] = _as_elapsed(mapped["timestamp"])
            derived.append("TransactionDT")
            notes.append("TransactionDT derived as elapsed seconds from the mapped timestamp.")

    if "ProductCD" not in data or data["ProductCD"].isna().all():
        sku = mapped["product_sku"] if "product_sku" in mapped.columns else None
        if sku is not None:
            coded = _product_cd(sku)
            if coded.notna().any():
                data["ProductCD"] = coded
                derived.append("ProductCD")
                notes.append("ProductCD used only when the product value is an IEEE code (W/C/H/R/S).")

    account = mapped["account_id"] if "account_id" in mapped.columns else None
    merchant = mapped["merchant"] if "merchant" in mapped.columns else None
    elapsed = data.get("TransactionDT")

    if account is not None and account.notna().any():
        if "card1" not in data or data["card1"].isna().all():
            data["card1"] = _hash_to_card1(account)
            derived.append("card1")
            notes.append("card1 is a hashed account identifier proxy, not an IEEE card number.")
        if "C1" not in data or data["C1"].isna().all():
            data["C1"] = _counts(account)
            derived.append("C1")
            notes.append("C1 is derived account frequency in the uploaded rows.")
        if elapsed is not None and ("C2" not in data or data["C2"].isna().all()):
            data["C2"] = _hourly_counts(account, elapsed)
            derived.append("C2")
            notes.append("C2 is derived account hourly velocity.")

    if merchant is not None and merchant.notna().any():
        if "C3" not in data or data["C3"].isna().all():
            data["C3"] = _counts(merchant)
            derived.append("C3")
            notes.append("C3 is derived merchant frequency.")
        if elapsed is not None and ("C4" not in data or data["C4"].isna().all()):
            data["C4"] = _hourly_counts(merchant, elapsed)
            derived.append("C4")
            notes.append("C4 is derived merchant hourly velocity.")

    if "DeviceInfo" not in data or data["DeviceInfo"].isna().all():
        if "device_id" in mapped.columns and mapped["device_id"].notna().any():
            data["DeviceInfo"] = mapped["device_id"].astype("string")
            derived.append("DeviceInfo")
            notes.append("DeviceInfo taken from the mapped device identifier.")

    if not notes:
        notes.append("Official IEEE-CIS columns used where present. Missing fields were not fabricated.")
    work = pd.DataFrame(data, index=mapped.index)
    return _finalize(world, work, derived=derived, notes=notes)


def adapt_synthetic(window: pd.DataFrame, *, world: str = "SYNTHETIC SCENARIO") -> Adaptation:
    work = pd.DataFrame(index=window.index)
    derived: list[str] = []
    notes = [
        "Synthetic amount, time, account velocity, and identifiers are derived into canonical slots.",
        "sku, pincode, and subnet are not IEEE-CIS features and are not passed through.",
    ]
    if "amount" in window.columns:
        work["TransactionAmt"] = pd.to_numeric(window["amount"], errors="coerce")
        derived.append("TransactionAmt")
    if "timestamp" in window.columns:
        work["TransactionDT"] = _as_elapsed(window["timestamp"])
        derived.append("TransactionDT")
    if "transaction_id" in window.columns:
        work[ID_COLUMN] = window["transaction_id"]
    if "account_id" in window.columns:
        work["card1"] = _hash_to_card1(window["account_id"])
        derived.append("card1")
        if "account_tx_count_1h" in window.columns:
            work["C1"] = pd.to_numeric(window["account_tx_count_1h"], errors="coerce")
            derived.append("C1")
        else:
            work["C1"] = _counts(window["account_id"])
            derived.append("C1")
        if "TransactionDT" in work.columns:
            work["C2"] = _hourly_counts(window["account_id"], work["TransactionDT"])
            derived.append("C2")
    if "device_id" in window.columns:
        work["DeviceInfo"] = window["device_id"].astype("string")
        derived.append("DeviceInfo")
    if "sku_id" in window.columns:
        coded = _product_cd(window["sku_id"])
        if coded.notna().any():
            work["ProductCD"] = coded
            derived.append("ProductCD")
    return _finalize(world, work, derived=derived, notes=notes)


def adaptation_status(adaptation: Adaptation) -> dict[str, Any]:
    return {
        "can_score": adaptation.can_score,
        "features_used": adaptation.features_used,
        "features_derived": adaptation.features_derived,
        "features_native": adaptation.features_native,
        "features_unavailable": adaptation.features_unavailable,
        "missing_required": adaptation.missing_required,
        "notes": adaptation.notes,
        "features_fabricated": False,
    }
