"""Chunked CSV IO for Bring Your Data. Never writes into benchmark dataset dirs."""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from evaluation.custom_data.mapping import apply_mapping
from evaluation.custom_data.schema import CustomDataError

CHUNK_ROWS = 10_000
SCORE_CHUNK_ROWS = 10_000
MAX_FIELD_BYTES = 8 * 1024 * 1024
TEMP_DIRNAME = "fraud-spike-investigator-byd"
TEMP_PREFIX = "byd-upload-"


def byd_temp_dir() -> Path:
    root = Path(tempfile.gettempdir()) / TEMP_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_upload_path(suffix: str = ".csv") -> Path:
    fd, raw = tempfile.mkstemp(prefix=TEMP_PREFIX, suffix=suffix, dir=byd_temp_dir())
    os.close(fd)
    return Path(raw)


def unlink_quietly(path: str | Path | None) -> None:
    if not path:
        return
    target = Path(path)
    try:
        if target.is_file():
            target.unlink()
    except OSError:
        pass


def configure_csv_parser() -> None:
    csv.field_size_limit(MAX_FIELD_BYTES)


def iter_csv_chunks(
    path: str | Path,
    chunksize: int = CHUNK_ROWS,
    usecols: list[str] | None = None,
) -> Iterator[pd.DataFrame]:
    configure_csv_parser()
    target = Path(path)
    try:
        reader = pd.read_csv(
            target,
            chunksize=chunksize,
            usecols=usecols,
            encoding="utf-8",
            encoding_errors="replace",
            low_memory=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise CustomDataError(f"The CSV could not be parsed: {exc}.") from exc
    try:
        for chunk in reader:
            yield chunk
    except Exception as exc:  # noqa: BLE001
        raise CustomDataError(f"The CSV could not be parsed: {exc}.") from exc


def iter_mapped_chunks(
    path: str | Path,
    mapping: dict[str, str],
    chunksize: int = CHUNK_ROWS,
) -> Iterator[pd.DataFrame]:
    wanted = [name for name in mapping.values() if name]
    usecols = wanted or None
    for chunk in iter_csv_chunks(path, chunksize=chunksize, usecols=usecols):
        yield apply_mapping(chunk, mapping)


def read_columns(path: str | Path) -> list[str]:
    configure_csv_parser()
    header = pd.read_csv(path, nrows=0, encoding="utf-8", encoding_errors="replace")
    columns = [str(name) for name in header.columns]
    if not columns:
        raise CustomDataError("The CSV has no rows or columns.")
    return columns
