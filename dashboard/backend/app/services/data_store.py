from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.core.config import METADATA_PATH, ONLINE_PATH, PREDICTION_PATH, SENSOR_FIELDS


class DataUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataBundle:
    frame: pd.DataFrame
    metadata: dict


def _read_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise DataUnavailableError(f"Berkas data tidak ditemukan: {path}")
    try:
        table = pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover - error text depends on parquet engine
        raise DataUnavailableError(f"Gagal membaca {path.name}: {exc}") from exc
    if "timestamp" in table.columns:
        table = table.set_index("timestamp")
    table.index = pd.to_datetime(table.index, errors="coerce")
    table = table.loc[~table.index.isna()].sort_index()
    table.index.name = "timestamp"
    return table


@lru_cache(maxsize=1)
def load_data() -> DataBundle:
    """Load the committed, preprocessed sensor timeline and honest walk-forward output."""
    online = _read_parquet(ONLINE_PATH)
    prediction = _read_parquet(PREDICTION_PATH)
    if online.index.has_duplicates:
        online = online.loc[~online.index.duplicated(keep="last")]
    if prediction.index.has_duplicates:
        prediction = prediction.loc[~prediction.index.duplicated(keep="last")]

    missing = [name for name in SENSOR_FIELDS if name not in online.columns and name != "data_ok"]
    if missing:
        raise DataUnavailableError(f"Kolom sensor tidak ditemukan: {', '.join(missing)}")
    columns = [name for name in SENSOR_FIELDS if name in online.columns]
    combined = online[columns].join(prediction, how="left", rsuffix="_prediction")
    combined["status_final"] = combined.get("status_final", pd.Series(index=combined.index, dtype=object)).fillna("Abu-abu")
    combined["pemicu_final"] = combined.get("pemicu_final", pd.Series(index=combined.index, dtype=object)).fillna("-")
    if "model_aktif" not in combined:
        combined["model_aktif"] = False
    combined["model_aktif"] = combined["model_aktif"].fillna(False).astype(bool)

    metadata: dict = {}
    if METADATA_PATH.exists():
        try:
            metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
    return DataBundle(frame=combined, metadata=metadata)


def clear_data_cache() -> None:
    load_data.cache_clear()


def json_value(value):
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def rul_stage(row: pd.Series) -> str | None:
    value = row.get("rul_pred")
    if pd.isna(value):
        return None
    hours = float(value)
    if hours <= 0:
        return "Failure"
    if hours <= 6:
        return "Critical"
    if hours <= 24:
        return "Warning"
    return "Normal"


def frame_payload(timestamp: pd.Timestamp, row: pd.Series) -> dict:
    sensors = {
        name: json_value(row.get(name))
        for name in SENSOR_FIELDS
        if name in row.index
    }
    probability = json_value(row.get("p_terkalibrasi"))
    return {
        "timestamp": timestamp.to_pydatetime(),
        "status": str(row.get("status_final") or "Abu-abu"),
        "trigger": json_value(row.get("pemicu_final")),
        "probability": probability,
        "rul_hours": json_value(row.get("rul_pred")),
        "rul_lower": json_value(row.get("rul_bawah")),
        "rul_upper": json_value(row.get("rul_atas")),
        "rul_stage": rul_stage(row),
        "model_active": bool(row.get("model_aktif", False)),
        "sensors": sensors,
    }
