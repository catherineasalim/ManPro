"""
Fungsi bersama untuk pemodelan model RUL, model anomali RF/XGBoost, kalibrasi, dan analisis.

Dipakai oleh:
  train_baseline.py          model baseline RUL dan anomali
  train_final_calibrated.py  model final terkalibrasi dan ekspor model
  analysis_report.py         laporan analisis: FP/FN, ROI, sensitivitas, pola degradasi

Prinsip yang sama dengan pipeline hybrid:
  - Split selalu menurut waktu. Tidak ada split acak, karena menit berdekatan hampir identik.
  - Ambang dan hiperparameter dipilih di dalam data latih (validasi dalam), tidak pernah dari bulan uji.
  - Label hanya untuk target dan penilaian, tidak pernah dijadikan fitur.
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    mean_absolute_error,
    precision_score,
    recall_score,
    roc_auc_score,
)

from anomaly_detection.common.evaluation import persist_alarm, to_episodes
from anomaly_detection.preprocessing.preprocess_dataprep import FAILURES, FEATURES, load_tables  # noqa: F401 (load_tables diekspor ulang)
from anomaly_detection.preprocessing.preprocess_iforest import EVENTS, FOLDS, MAINTENANCE_GAPS, MARGIN, N_JOBS, OUTPUT_DIR, SEED, event_masks  # noqa: F401 (FOLDS diekspor ulang)
from anomaly_detection.preprocessing.preprocess_supervised import LABEL_COVERAGE

MODEL_DIR = OUTPUT_DIR / "model"
CHART_DIR = MODEL_DIR / "grafik"
FINAL_DIR = MODEL_DIR / "final"

RUL_CAP = 72.0
STAGE_EDGES = (6.0, 24.0)  # Critical <= 6 jam, Warning 6-24 jam, Normal > 24 jam. Sama dengan RUL_Stage.
STAGE_NAMES = ["Critical", "Warning", "Normal"]
HEALTHY_STEP = 5  # Baris sehat (RUL = 72) diambil tiap 5 menit agar tidak menenggelamkan baris degradasi.
RUL_SMOOTH_MIN = 30  # Prediksi RUL dihaluskan dengan median 30 menit sebelum dipakai untuk alarm.

# Segmen k = periode normal lalu failure k (lihat add_labels di preprocess_dataprep.py). Segmen 5 tanpa failure.
RUL_TEST_SEGMENTS = (2, 3, 4, 5)

# Warna grafik: palet kategorikal referensi (slot 1-3) dan warna status yang dicadangkan.
COLORS = {"s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a", "muted": "#8a8984", "critical": "#d03b3b", "text": "#0b0b0b"}


def ensure_dirs():
    for d in (MODEL_DIR, CHART_DIR, FINAL_DIR):
        d.mkdir(parents=True, exist_ok=True)


def save_json(obj, path):
    def default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if isinstance(o, (pd.Timestamp,)):
            return str(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(type(o))

    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=default), encoding="utf-8")


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
def make_classifier(kind, seed=SEED, **params):
    if kind == "rf":
        from sklearn.ensemble import RandomForestClassifier

        return RandomForestClassifier(
            n_estimators=params.get("n_estimators", 200),
            max_depth=params.get("max_depth", 12),
            min_samples_leaf=params.get("min_samples_leaf", 5),
            class_weight="balanced_subsample",
            max_samples=params.get("max_samples", 50_000),
            n_jobs=N_JOBS,
            random_state=seed,
        )
    from xgboost import XGBClassifier

    return XGBClassifier(
        n_estimators=params.get("n_estimators", 300),
        max_depth=params.get("max_depth", 4),
        learning_rate=params.get("learning_rate", 0.05),
        subsample=params.get("subsample", 0.8),
        colsample_bytree=params.get("colsample_bytree", 0.8),
        min_child_weight=params.get("min_child_weight", 5),
        reg_lambda=params.get("reg_lambda", 1.0),
        scale_pos_weight=params.get("scale_pos_weight", 1.0),
        tree_method="hist",
        n_jobs=N_JOBS,
        random_state=seed,
        eval_metric="logloss",
    )


def make_regressor(kind, seed=SEED, **params):
    if kind == "rf":
        from sklearn.ensemble import RandomForestRegressor

        return RandomForestRegressor(
            n_estimators=params.get("n_estimators", 200),
            max_depth=params.get("max_depth", 14),
            min_samples_leaf=params.get("min_samples_leaf", 10),
            max_samples=params.get("max_samples", 50_000),
            max_features=params.get("max_features", 0.5),
            n_jobs=N_JOBS,
            random_state=seed,
        )
    from xgboost import XGBRegressor

    return XGBRegressor(
        n_estimators=params.get("n_estimators", 400),
        max_depth=params.get("max_depth", 5),
        learning_rate=params.get("learning_rate", 0.05),
        subsample=params.get("subsample", 0.8),
        colsample_bytree=params.get("colsample_bytree", 0.8),
        min_child_weight=params.get("min_child_weight", 10),
        reg_lambda=params.get("reg_lambda", 1.0),
        tree_method="hist",
        n_jobs=N_JOBS,
        random_state=seed,
        objective="reg:squarederror",
    )


class MedianImputer:
    """Random Forest sklearn tidak menerima NaN. Median dihitung dari data latih saja."""

    def fit(self, X):
        self.medians_ = np.nanmedian(X, axis=0)
        self.medians_ = np.where(np.isnan(self.medians_), 0.0, self.medians_)
        return self

    def transform(self, X):
        X = X.copy()
        rows, cols = np.where(np.isnan(X))
        X[rows, cols] = self.medians_[cols]
        return X


def needs_imputer(kind):
    return kind == "rf"


# ---------------------------------------------------------------------------
# Data anomali (klasifikasi kejadian)
# ---------------------------------------------------------------------------
def anomaly_train_rows(train_table, cut, events=EVENTS, start=None):
    """Positif: menit di dalam kejadian yang selesai sebelum 'cut'. Negatif: baris usable_train di periode berlabel.

    Sama dengan labeled_rows di train_hgb_dataprep.py, tetapi memakai ke-51 fitur.
    """
    rows = train_table[train_table.index < cut]
    if start is not None:
        rows = rows[rows.index >= start]
    y, outside_zone, n_events = event_masks(rows.index, events, cut=cut)
    labeled_period = (rows.index >= LABEL_COVERAGE[0]) & (rows.index < LABEL_COVERAGE[1])
    positive = (y == 1) & rows["data_ok"].to_numpy()
    negative = (y == 0) & outside_zone & rows["usable_train"].to_numpy() & labeled_period
    keep = positive | negative
    return rows.loc[keep, FEATURES], y[keep], n_events


def anomaly_test_rows(online_table):
    keep = online_table["data_ok"] & ~online_table["in_grace"]
    return online_table.loc[keep, FEATURES]


def row_labels(index, events=EVENTS):
    y = np.zeros(len(index), dtype=np.int8)
    neutral = np.zeros(len(index), dtype=bool)
    for e in events.itertuples():
        y[(index >= e.start) & (index <= e.end)] = 1
        neutral |= (index >= e.start - MARGIN) & (index <= e.end + MARGIN)
    for a, b in MAINTENANCE_GAPS:
        neutral |= (index >= a) & (index <= b)
    return y, neutral & (y == 0)


def row_metrics(scores, threshold, events=EVENTS):
    """Metrik per baris. Margin 2 jam di sekitar kejadian tidak dihitung, sama seperti average_precision di evaluation.py."""
    y, neutral = row_labels(scores.index, events)
    used = ~neutral
    y, p = y[used], scores.to_numpy()[used]
    pred = p > threshold
    out = {
        "baris_dinilai": int(used.sum()),
        "baris_positif": int(y.sum()),
        "precision_baris": precision_score(y, pred, zero_division=0),
        "recall_baris": recall_score(y, pred, zero_division=0),
        "f1_baris": f1_score(y, pred, zero_division=0),
        "roc_auc": roc_auc_score(y, p) if 0 < y.sum() < len(y) else np.nan,
        "pr_auc": average_precision_score(y, p) if y.sum() else np.nan,
        "brier": brier_score_loss(y, np.clip(p, 0, 1)),
        "tp": int((pred & (y == 1)).sum()),
        "fp": int((pred & (y == 0)).sum()),
        "fn": int((~pred & (y == 1)).sum()),
        "tn": int((~pred & (y == 0)).sum()),
    }
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def event_level(alarm, events, period_start, period_end):
    """Penilaian per kejadian untuk periode dan daftar kejadian mana pun (versi umum dari evaluation.evaluate).

    alarm: Series boolean (sesudah persist_alarm). Kejadian terdeteksi jika ada alarm antara 2 jam sebelum mulai dan
    akhir kejadian. Alarm palsu: episode yang tidak menyentuh kejadian, margin, atau jeda perbaikan.
    """
    episodes = [(a, b) for a, b in to_episodes(alarm) if b >= period_start and a < period_end]
    events = events[(events["start"] >= period_start) & (events["start"] < period_end)]
    first = {}
    for e in events.itertuples():
        low = e.start - MARGIN
        hits = [max(a, low) for a, b in episodes if a <= e.end and b >= low]
        first[e.id] = min(hits) if hits else None

    def known(a, b):
        near_event = any(a <= e.end + MARGIN and b >= e.start - MARGIN for e in EVENTS.itertuples())
        near_gap = any(a <= gb and b >= ga for ga, gb in MAINTENANCE_GAPS)
        return near_event or near_gap

    false_alarms = [(a, b) for a, b in episodes if not known(a, b)]
    starts = events.set_index("id")["start"]
    delays = [(t - starts[k]).total_seconds() / 60 for k, t in first.items() if t is not None]
    hits = sum(t is not None for t in first.values())
    n = len(events)
    recall = hits / n if n else np.nan
    precision = (len(episodes) - len(false_alarms)) / len(episodes) if episodes else 0.0
    return {
        "first_alarm": first,
        "false_alarms": false_alarms,
        "episodes": episodes,
        "hits": hits,
        "n_events": n,
        "recall": recall,
        "precision": precision,
        "median_delay": float(np.median(delays)) if delays else np.nan,
    }


def alarm_cost(result, weeks, cost_fn, cost_fp):
    """Biaya relatif: kejadian terlewat dan alarm palsu, dinormalisasi per minggu."""
    missed = result["n_events"] - result["hits"]
    return (cost_fn * missed + cost_fp * len(result["false_alarms"])) / max(weeks, 1e-9)


# ---------------------------------------------------------------------------
# Data RUL
# ---------------------------------------------------------------------------
def rul_rows(table, segments, healthy_step=None):
    """Baris dengan RUL diketahui (bukan grace, data_ok). Baris sehat bisa dijarangkan untuk latih."""
    keep = table["data_ok"].to_numpy() & ~table["in_grace"].to_numpy() & table["RUL_Hours"].notna().to_numpy()
    keep &= table["segment"].isin(segments).to_numpy()
    rows = table.loc[keep]
    if healthy_step:
        healthy = rows["RUL_Hours"].to_numpy() >= RUL_CAP
        minute = rows.index.minute.to_numpy()
        rows = rows[~healthy | (minute % healthy_step == 0)]
    return rows


def rul_stage(values):
    values = np.asarray(values, dtype=float)
    return np.select([values <= STAGE_EDGES[0], values <= STAGE_EDGES[1]], STAGE_NAMES[:2], STAGE_NAMES[2])


def nasa_score(true, pred):
    """Fungsi skor PHM08 (Saxena dkk., 2008). Prediksi terlambat (RUL terlalu besar) dihukum lebih berat. Rata-rata per baris."""
    d = np.asarray(pred) - np.asarray(true)
    s = np.where(d < 0, np.exp(-d / 13.0) - 1, np.exp(d / 10.0) - 1)
    return float(np.mean(s))


def smooth_rul(pred):
    """Median 30 menit ke belakang, agar alarm RUL tidak berkedip."""
    return pred.rolling(f"{RUL_SMOOTH_MIN}min", min_periods=5).median()


def rul_alert_eval(pred, segment_rows, alert_hours, persist=True):
    """Alarm RUL: prediksi (sudah dihaluskan) di bawah alert_hours.

    Lead time  : jam dari alarm pertama (dalam 72 jam sebelum failure) sampai failure mulai.
    Alarm palsu: episode alarm yang mulai lebih dari 72 jam sebelum failure berikutnya, atau di segmen tanpa failure.
    """
    alarm = pred < alert_hours
    if persist:
        alarm = persist_alarm(alarm)
    episodes = to_episodes(alarm)
    seg_end = segment_rows.index.max()
    upcoming = FAILURES[(FAILURES["start"] >= segment_rows.index.min()) & (FAILURES["start"] <= seg_end + pd.Timedelta(hours=1))]
    if len(upcoming):
        f = upcoming.iloc[0]
        window_start = f["start"] - pd.Timedelta(hours=RUL_CAP)
        hits = [a for a, b in episodes if b >= window_start and a <= f["end"]]
        first = min(hits) if hits else None
        lead = (f["start"] - max(first, window_start)).total_seconds() / 3600 if first is not None else np.nan
        false_eps = [(a, b) for a, b in episodes if b < window_start]
        detected = first is not None and first <= f["start"]
    else:
        lead, false_eps, detected, first = np.nan, episodes, None, None
    return {"terdeteksi_sebelum_failure": detected, "lead_time_jam": lead, "alarm_palsu": len(false_eps), "alarm_pertama": first}


def rul_metrics(true, pred):
    true, pred = np.asarray(true, float), np.asarray(pred, float)
    degr = true < RUL_CAP
    pre = (true > 0) & (true < RUL_CAP)
    crit = true <= STAGE_EDGES[1]
    true_stage, pred_stage = rul_stage(true), rul_stage(pred)
    out = {
        "mae_semua": mean_absolute_error(true, pred),
        "rmse_semua": float(np.sqrt(np.mean((true - pred) ** 2))),
        "mae_degradasi": mean_absolute_error(true[degr], pred[degr]) if degr.any() else np.nan,
        "rmse_degradasi": float(np.sqrt(np.mean((true[degr] - pred[degr]) ** 2))) if degr.any() else np.nan,
        "mae_kritis_24j": mean_absolute_error(true[crit], pred[crit]) if crit.any() else np.nan,
        "nasa_skor_degradasi": nasa_score(true[degr], pred[degr]) if degr.any() else np.nan,
        "akurasi_stage": float(np.mean(true_stage == pred_stage)),
        "f1_makro_stage": f1_score(true_stage, pred_stage, labels=STAGE_NAMES, average="macro", zero_division=0),
        "recall_critical": recall_score(true_stage == "Critical", pred_stage == "Critical", zero_division=0) if (true_stage == "Critical").any() else np.nan,
        "n_baris": int(len(true)),
        "n_degradasi": int(degr.sum()),
        "mae_pra_failure": mean_absolute_error(true[pre], pred[pre]) if pre.any() else np.nan,
    }
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def segment_window(seg):
    """Rentang waktu satu segmen (dipakai untuk label grafik)."""
    return {1: "Feb-F1", 2: "F1-F2", 3: "F2-F3", 4: "F3-F4", 5: "sesudah F4"}[seg]

