from __future__ import annotations

import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = BACKEND_DIR.parent
REPO_ROOT = DASHBOARD_DIR.parent
try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
except ImportError:  # pragma: no cover - requirements install python-dotenv
    pass

DATA_DIR = REPO_ROOT / "anomaly_detection" / "output"
ONLINE_PATH = DATA_DIR / "dataprep" / "dataset_online_1min.parquet"
PREDICTION_PATH = DATA_DIR / "model" / "prediksi_walkforward.parquet"
METADATA_PATH = DATA_DIR / "model" / "final" / "metadata.json"
API_PREFIX = os.getenv("DASHBOARD_API_PREFIX", "/api")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DASHBOARD_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]

SENSOR_FIELDS = (
    "TP2",
    "TP3",
    "Oil_temperature",
    "Motor_current",
    "COMP",
    "DV_eletric",
    "Towers",
    "H1",
    "data_ok",
)
STATUS_RANK = {"Abu-abu": -1, "Hijau": 0, "Kuning": 1, "Merah": 2}
