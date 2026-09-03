"""Helpers for JSON-safe evidence values."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def as_int(value: Any) -> int:
    return int(value)


def as_float(value: Any, digits: int = 4) -> float:
    return round(float(value), digits)


def json_safe(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if pd.isna(number):
            return None
        return number
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value
