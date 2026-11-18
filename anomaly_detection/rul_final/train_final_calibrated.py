"""
Model final RUL dan deteksi anomali yang terkalibrasi, dengan ambang teroptimasi, lalu diekspor.

Jalankan:  python -m anomaly_detection.rul_final.train_final_calibrated        (sesudah train_baseline.py dan train_hybrid.py)
Pilihan:   --seed 42  --cost-ratio 10
Hasil:     output/model/
             final_anomali.csv               ringkasan walk-forward model final vs baseline vs hybrid lama
             final_rul.csv, final_rul_per_segmen.csv
             final_target.csv                pemeriksaan target metrik (lulus / tidak)
             final_pilihan_per_putaran.csv   model, hiperparameter, dan ambang yang dipilih tiap putaran
             prediksi_walkforward.parquet    skor per menit April-Agustus (untuk analysis_report.py dan dashboard)
           output/model/final/
             model_final.joblib                bundel model untuk data baru (dipakai predict.py)
             anomali_xgb_*.json, rul_xgb.json  model XGBoost dalam format asli (bisa dibuka tanpa Python)
             metadata.json                   fitur, ambang, kalibrasi, versi pustaka, dan metrik walk-forward

Semua pilihan dibuat di dalam data latih tiap putaran (validasi dalam), tidak pernah dari bulan atau segmen uji:

Anomali (per putaran bulan Mei-Agustus; April tanpa label sehingga tetap memakai aturan cold start IsolationForest)
  1. Validasi dalam: kejadian yang sudah diketahui dikelompokkan (kejadian berjarak < 3 hari satu kelompok),
     lalu GroupKFold menghasilkan skor out-of-fold untuk seluruh baris latih.
  2. Pilih kandidat (XGBoost dua konfigurasi, Random Forest, atau rata-rata ketiganya) dengan biaya kejadian terkecil.
  3. Kalibrasi isotonic dari skor out-of-fold, supaya skor 0,8 berarti sekitar 80% menit seperti itu memang kejadian.
  4. Ambang dipilih dari skor terkalibrasi out-of-fold: biaya = cost_ratio x kejadian terlewat + alarm palsu.
  5. Skor terkalibrasi menggantikan HGB di sistem hybrid (hybrid.combine_status), aturan status lain tidak berubah.

RUL (per segmen uji 2-5)
  1. Validasi dalam expanding-window: segmen latih ke-i divalidasi dengan model dari segmen sebelumnya saja.
     Segmen uji 2 hanya punya satu segmen latih, sehingga segmen 1 dibagi 4 blok waktu berurutan dan tiap blok
     divalidasi dengan model dari blok sebelumnya.
  2. Pilih hiperparameter XGBoost dengan MAE pra-failure (0 < RUL < 72 jam) terkecil.
  3. Kalibrasi interval: conformal split dari residu out-of-fold, terpisah per rentang prediksi (Mondrian),
     target cakupan 80%.
  3b. Kalibrasi titik: isotonic dari prediksi out-of-fold ke RUL nyata (menghapus bias ke bawah pada baris sehat).
  4. Ambang alarm RUL dipilih dari prediksi out-of-fold dengan biaya yang sama seperti anomali.
  5. Saat model anomali terkalibrasi menyatakan alarm (pola kegagalan sedang berlangsung), RUL ditetapkan 0 (stage
     Failure). Regresi saja hampir tidak bisa mengenali kondisi gagal karena barisnya sedikit.

Target metrik ditulis di TARGETS sebelum model final dijalankan. Hasilnya dilaporkan apa adanya, lulus atau tidak.
"""
import argparse
import platform
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import GroupKFold

from anomaly_detection.common.model_utils import (
    MODEL_DIR,
    FEATURES,
    FINAL_DIR,
    FOLDS,
    HEALTHY_STEP,
    RUL_CAP,
    RUL_TEST_SEGMENTS,
    SEED,
    MedianImputer,
    anomaly_test_rows,
    anomaly_train_rows,
    ensure_dirs,
    event_level,
    load_tables,
    make_classifier,
    make_regressor,
    needs_imputer,
    row_metrics,
    rul_alert_eval,
    rul_metrics,
    rul_rows,
    save_json,
    smooth_rul,
)
from anomaly_detection.common.evaluation import TEST_WEEKS, evaluate, persist_alarm, to_episodes
from anomaly_detection.common.hybrid import combine_status, red_alarm, warning_alarm
from anomaly_detection.anomali.model_iforest import fit_iforest
from anomaly_detection.preprocessing.preprocess_iforest import EVENTS, OUTPUT_DIR, TRAIN_DAYS
from anomaly_detection.anomali.train_hybrid import normal_rows as hybrid_normal_rows
from anomaly_detection.preprocessing.preprocess_supervised import LABEL_COVERAGE

MAY = pd.Timestamp("2020-05-01")
HYBRID_DIR = OUTPUT_DIR / "hybrid"

# Kandidat model anomali. Sedikit saja: hanya 16 kejadian, grid besar akan menyetel ke kejadian yang sama.
ANOMALY_CANDIDATES = {
    "xgb_dangkal": ("xgb", {"max_depth": 3, "n_estimators": 300, "learning_rate": 0.05, "min_child_weight": 20}),
    "xgb_sedang": ("xgb", {"max_depth": 5, "n_estimators": 300, "learning_rate": 0.05, "min_child_weight": 5}),
    "rf": ("rf", {"n_estimators": 200, "max_depth": 12, "min_samples_leaf": 5}),
}
THRESHOLD_GRID = np.round(np.arange(0.10, 0.951, 0.05), 2)
GROUP_GAP = pd.Timedelta(days=3)

RUL_CANDIDATES = {
    "dangkal": {"max_depth": 3, "n_estimators": 300, "min_child_weight": 50},
    "sedang": {"max_depth": 5, "n_estimators": 400, "min_child_weight": 10},
    "dalam": {"max_depth": 7, "n_estimators": 300, "min_child_weight": 20, "subsample": 0.7},
}
RUL_DEFAULT = "sedang"
RUL_ALERT_GRID = (6.0, 12.0, 24.0, 36.0, 48.0)
RUL_DEFAULT_ALERT = 24.0
COVERAGE = 0.80
CONFORMAL_BINS = (0.0, 24.0, 60.0, RUL_CAP + 1)  # Rentang prediksi untuk conformal Mondrian.

# Ditetapkan sesudah melihat baseline, sebelum menjalankan model final.
TARGETS = [
    ("Anomali", "Hybrid Merah: kejadian terdeteksi", ">=", 14, "kejadian"),
    ("Anomali", "Hybrid Merah: kegagalan resmi terdeteksi", ">=", 4, "resmi"),
    ("Anomali", "Hybrid Merah: alarm palsu per minggu", "<=", 0.25, "palsu_per_minggu"),
    ("Anomali", "Model terkalibrasi: Brier skor Mei-Agu", "<=", None, "brier"),  # Pembanding: baseline XGBoost.
    ("Anomali", "Model terkalibrasi: ECE Mei-Agu", "<=", 0.05, "ece"),
    ("RUL", "MAE sebelum failure (jam)", "<=", 12.0, "mae_pra"),
    ("RUL", "Cakupan interval 80%", "antara", (0.70, 0.90), "cakupan"),
    ("RUL", "Failure diperingatkan sebelum mulai (segmen 2-4)", ">=", 2, "terdeteksi"),
    ("RUL", "Alarm RUL palsu per bulan", "<=", 1.0, "palsu_per_bulan"),
]


# ---------------------------------------------------------------------------
# Anomali
# ---------------------------------------------------------------------------
def fit_model(kind, params, X, y, seed):
    X = X.to_numpy("float32") if hasattr(X, "to_numpy") else X
    imputer = MedianImputer().fit(X) if needs_imputer(kind) else None
    if imputer is not None:
        X = imputer.transform(X)
    params = dict(params)
    if kind == "xgb":
        params["scale_pos_weight"] = float((y == 0).sum() / max((y == 1).sum(), 1))
    model = make_classifier(kind, seed, **params)
    ms = model.get_params().get("max_samples")
    if ms is not None and ms > len(X):
        model.set_params(max_samples=None)
    return model.fit(X, y), imputer


def raw_proba(model, imputer, X):
    X = X.to_numpy("float32") if hasattr(X, "to_numpy") else X
    if imputer is not None:
        X = imputer.transform(X)
    return model.predict_proba(X)[:, 1]


def event_groups(index, events):
    """Setiap baris masuk kelompok kejadian terdekat. Kejadian berjarak < 3 hari digabung agar tidak bocor antar-fold."""
    events = events.sort_values("start")
    cluster, last_end, ids = -1, None, []
    for e in events.itertuples():
        if last_end is None or e.start - last_end > GROUP_GAP:
            cluster += 1
        ids.append(cluster)
        last_end = e.end if last_end is None else max(last_end, e.end)
    mids = (events["start"] + (events["end"] - events["start"]) / 2).to_numpy()
    t = index.to_numpy()
    nearest = np.abs(t[:, None] - mids[None, :]).argmin(axis=1)
    return np.asarray(ids)[nearest], cluster + 1


def best_threshold(oof, known, period_start, period_end, weeks, cost_ratio):
    """Ambang dengan biaya terkecil pada skor out-of-fold. Jika sama, ambang yang lebih tinggi (alarm lebih sedikit)."""
    best = None
    for thr in THRESHOLD_GRID:
        result = event_level(persist_alarm(oof > thr), known, period_start, period_end)
        cost = (cost_ratio * (result["n_events"] - result["hits"]) + len(result["false_alarms"])) / weeks
        if best is None or cost <= best[1] + 1e-12:
            best = (thr, cost, result["hits"], result["n_events"], len(result["false_alarms"]))
    return best


def candidate_members(name):
    """Kandidat 'ensemble' = rata-rata skor mentah semua model tunggal."""
    if name == "ensemble":
        return [n for n in ANOMALY_CANDIDATES]
    return [name]


def inner_anomaly(X, y, index, known, seed, cost_ratio):
    """Validasi dalam: pilih kandidat, kalibrasi isotonic, dan ambang. Semuanya dari data latih saja."""
    groups, n_groups = event_groups(index, known)
    if n_groups < 2:
        # Satu kelompok kejadian saja: tidak ada validasi dalam. Pakai kandidat pertama tanpa kalibrasi, ambang 0,5.
        return next(iter(ANOMALY_CANDIDATES)), {"iso": None, "threshold": 0.5, "cost": np.nan, "hits": np.nan, "n": np.nan, "fa": np.nan, "pr_auc": np.nan}
    splitter = GroupKFold(n_splits=min(5, n_groups))
    period_start = max(index.min(), LABEL_COVERAGE[0])
    period_end = index.max() + pd.Timedelta(minutes=1)
    weeks = (period_end - period_start).total_seconds() / (7 * 86400)

    oof = {}
    for name, (kind, params) in ANOMALY_CANDIDATES.items():
        scores = np.zeros(len(y))
        for tr, va in splitter.split(X, y, groups):
            if y[tr].sum() == 0:
                continue
            model, imputer = fit_model(kind, params, X.iloc[tr], y[tr], seed)
            scores[va] = raw_proba(model, imputer, X.iloc[va])
        oof[name] = scores
    oof["ensemble"] = np.mean([oof[n] for n in ANOMALY_CANDIDATES], axis=0)

    results = {}
    for name, scores in oof.items():
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(scores, y)
        calibrated = pd.Series(iso.predict(scores), index=index)
        thr, cost, hits, n, fa = best_threshold(calibrated, known, period_start, period_end, weeks, cost_ratio)
        results[name] = {"iso": iso, "threshold": thr, "cost": cost, "hits": hits, "n": n, "fa": fa, "pr_auc": average_precision_score(y, scores)}
    chosen = min(results, key=lambda k: (results[k]["cost"], -results[k]["pr_auc"]))
    return chosen, results[chosen]


def fit_members(name, X, y, seed):
    return [fit_model(*ANOMALY_CANDIDATES[m], X, y, seed) for m in candidate_members(name)]


def members_proba(members, X):
    return np.mean([raw_proba(model, imputer, X) for model, imputer in members], axis=0)


def calibrate(iso, p):
    return p if iso is None else iso.predict(p)


def anomaly_walk_forward(train_table, test, seed, cost_ratio):
    parts, choices = [], []
    for start, end in FOLDS:
        fold_test = test[(test.index >= start) & (test.index < end)]
        X, y, n_events = anomaly_train_rows(train_table, start)
        if n_events == 0:
            parts.append(pd.DataFrame({"p_raw": 0.0, "p_cal": 0.0, "thr": 1.0, "aktif": False}, index=fold_test.index))
            choices.append({"bulan": f"{start:%b}", "kejadian_diketahui": 0, "model": "-", "ambang": np.nan})
            continue
        known = EVENTS[EVENTS["end"] < start]
        t0 = time.time()
        name, info = inner_anomaly(X, y, X.index, known, seed, cost_ratio)
        p_raw = members_proba(fit_members(name, X, y, seed), fold_test)
        parts.append(pd.DataFrame({"p_raw": p_raw, "p_cal": calibrate(info["iso"], p_raw), "thr": info["threshold"], "aktif": True}, index=fold_test.index))
        choices.append(
            {
                "bulan": f"{start:%b}",
                "kejadian_diketahui": n_events,
                "model": name,
                "ambang": info["threshold"],
                "dalam_kejadian": f"{info['hits']}/{info['n']}",
                "dalam_alarm_palsu": info["fa"],
                "dalam_pr_auc": round(info["pr_auc"], 4) if not pd.isna(info["pr_auc"]) else np.nan,
            }
        )
        print(f"  anomali {start:%b}: {name}, ambang {info['threshold']}, {time.time() - t0:.0f} detik", flush=True)
    return pd.concat(parts).sort_index(), pd.DataFrame(choices)


def ece(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            total += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(total)


def calibration_table(scores, bins=10):
    from anomaly_detection.common.model_utils import row_labels

    y, neutral = row_labels(scores.index)
    y, p = y[~neutral], scores.to_numpy()[~neutral]
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    rows = [{"bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}", "n": int((idx == b).sum()), "rata_prediksi": float(p[idx == b].mean()) if (idx == b).any() else np.nan, "frekuensi_nyata": float(y[idx == b].mean()) if (idx == b).any() else np.nan} for b in range(bins)]
    return pd.DataFrame(rows), ece(y, p, bins)


def summarize_alarm(name, alarm):
    result = evaluate(to_episodes(alarm))
    first = result["first_alarm"]
    official = EVENTS.loc[EVENTS["official"], "id"]
    return {
        "metode": name,
        "kejadian": f"{result['hits']}/{len(EVENTS)}",
        "resmi": f"{sum(first[i] is not None for i in official)}/{len(official)}",
        "alarm_palsu": len(result["false_alarms"]),
        "palsu_per_minggu": round(len(result["false_alarms"]) / TEST_WEEKS, 3),
        "precision_kejadian": round(result["precision"], 3),
        "recall_kejadian": round(result["recall"], 3),
        "f1_kejadian": round(result["f1"], 3),
        "delay_median_menit": result["median_delay"],
        "meleset": ",".join(k for k, t in first.items() if t is None),
    }


def hybrid_frames(scores):
    """Sistem hybrid lama (HGB 0,5) dan baru (XGBoost terkalibrasi + ambang teroptimasi) pada menit yang sama."""
    status = pd.read_parquet(HYBRID_DIR / "status_walkforward.parquet")
    base = status.loc[scores.index, ["if_score", "if_threshold", "hgb_score", "hgb_threshold", "hgb_aktif"]].copy()
    old = combine_status(base)
    new_input = base.assign(hgb_score=scores["p_cal"].to_numpy(), hgb_threshold=scores["thr"].to_numpy(), hgb_aktif=scores["aktif"].to_numpy())
    new = combine_status(new_input)
    return old, new


# ---------------------------------------------------------------------------
# RUL
# ---------------------------------------------------------------------------
def fit_rul(params, rows, seed):
    model = make_regressor("xgb", seed, **params)
    return model.fit(rows[FEATURES].to_numpy("float32"), rows["RUL_Hours"].to_numpy())


def predict_rul_series(model, rows):
    pred = pd.Series(np.clip(model.predict(rows[FEATURES].to_numpy("float32")), 0, RUL_CAP), index=rows.index)
    return smooth_rul(pred).fillna(pred)


def conformal_bins(pred):
    return np.clip(np.digitize(pred, CONFORMAL_BINS[1:-1]), 0, len(CONFORMAL_BINS) - 2)


def fit_conformal(true, pred):
    """Kuantil residu per rentang prediksi. Interval = prediksi + [q_bawah, q_atas]."""
    resid = np.asarray(true) - np.asarray(pred)
    b = conformal_bins(np.asarray(pred))
    lo_q, hi_q = (1 - COVERAGE) / 2, 1 - (1 - COVERAGE) / 2
    overall = (np.quantile(resid, lo_q), np.quantile(resid, hi_q))
    table = {}
    for k in range(len(CONFORMAL_BINS) - 1):
        r = resid[b == k]
        table[k] = (float(np.quantile(r, lo_q)), float(np.quantile(r, hi_q))) if len(r) >= 50 else (float(overall[0]), float(overall[1]))
    return table


def apply_conformal(table, pred):
    pred = np.asarray(pred)
    b = conformal_bins(pred)
    lo = np.array([table[k][0] for k in b])
    hi = np.array([table[k][1] for k in b])
    # Interval selalu memuat titik prediksi sendiri, supaya tampilan dashboard tidak membingungkan.
    return np.clip(np.minimum(pred + lo, pred), 0, RUL_CAP), np.clip(np.maximum(pred + hi, pred), 0, RUL_CAP)


def inner_splits(train_table, segments, n_blocks=4):
    """Expanding window: setiap validasi hanya dilatih dengan data yang lebih awal.

    >= 2 segmen latih: segmen ke-i divalidasi dengan model dari segmen 1..i-1.
    Hanya 1 segmen: dibagi menjadi n_blocks blok waktu, blok ke-j divalidasi dengan model dari blok 1..j-1.
    """
    segments = sorted(segments)
    if len(segments) >= 2:
        for i in range(1, len(segments)):
            yield rul_rows(train_table, segments[:i], HEALTHY_STEP), rul_rows(train_table, [segments[i]])
        return
    rows = rul_rows(train_table, segments).sort_index()
    edges = np.linspace(0, len(rows), n_blocks + 1).astype(int)
    for a, b in zip(edges[1:-1], edges[2:]):
        train, valid = rows.iloc[:a], rows.iloc[a:b]
        healthy = train["RUL_Hours"].to_numpy() >= RUL_CAP
        yield train[~healthy | (train.index.minute.to_numpy() % HEALTHY_STEP == 0)], valid


def fit_isotonic_rul(pred, true):
    """Kalibrasi titik: petakan prediksi mentah ke rata-rata RUL nyata pada prediksi itu (monoton naik)."""
    return IsotonicRegression(increasing=True, y_min=0, y_max=RUL_CAP, out_of_bounds="clip").fit(pred, true)


def inner_rul(train_table, segments, seed, cost_ratio):
    """Validasi dalam untuk RUL: hiperparameter, kalibrasi isotonic, conformal, dan ambang alarm."""
    splits = list(inner_splits(train_table, segments))
    oof = {}
    for name, params in RUL_CANDIDATES.items():
        oof[name] = pd.concat([predict_rul_series(fit_rul(params, train, seed), valid) for train, valid in splits]).sort_index()
    true_all = train_table.loc[next(iter(oof.values())).index, "RUL_Hours"]

    scores, isos = {}, {}
    for name, pred in oof.items():
        isos[name] = fit_isotonic_rul(pred.to_numpy(), true_all.to_numpy())
        m = rul_metrics(true_all, isos[name].predict(pred.to_numpy()))
        # Dipilih dari MAE pra-failure (0 < RUL < 72 jam); MAE semua baris didominasi menit sehat.
        pra = m["mae_pra_failure"]
        scores[name] = pra if not pd.isna(pra) else (m["mae_semua"] + m["mae_degradasi"]) / 2
    chosen = min(scores, key=scores.get)
    iso = isos[chosen]
    pred = pd.Series(iso.predict(oof[chosen].to_numpy()), index=oof[chosen].index)
    conformal = fit_conformal(true_all.to_numpy(), pred.to_numpy())

    months = sum((valid.index.max() - valid.index.min()).total_seconds() / (30 * 86400) for _, valid in splits)
    best = None
    for alert in RUL_ALERT_GRID:
        missed = fa = 0
        leads = []
        for _, valid in splits:
            r = rul_alert_eval(pred.loc[valid.index], valid, alert)
            missed += r["terdeteksi_sebelum_failure"] is False
            fa += r["alarm_palsu"]
            if not pd.isna(r["lead_time_jam"]):
                leads.append(r["lead_time_jam"])
        cost = (cost_ratio * missed + fa) / max(months, 1e-9)
        key = (cost, -np.median(leads) if leads else 0.0)
        if best is None or key < best[0]:
            best = (key, alert)
    return chosen, iso, conformal, best[1], scores


def rul_walk_forward(train_table, online_table, failure_state, seed, cost_ratio):
    """failure_state: alarm model anomali terkalibrasi (walk-forward). Saat menyala, RUL ditetapkan 0 (stage Failure)."""
    rows, preds, choices = [], [], []
    for k in RUL_TEST_SEGMENTS:
        segments = list(range(1, k))
        t0 = time.time()
        name, iso, conformal, alert, inner_scores = inner_rul(train_table, segments, seed, cost_ratio)
        model = fit_rul(RUL_CANDIDATES[name], rul_rows(train_table, segments, HEALTHY_STEP), seed)
        test = rul_rows(online_table, [k])
        prognostic = pd.Series(iso.predict(predict_rul_series(model, test).to_numpy()), index=test.index)
        failing = failure_state.reindex(test.index).fillna(False).to_numpy(bool)
        pred = prognostic.where(~failing, 0.0)
        lo, hi = apply_conformal(conformal, pred.to_numpy())
        true = test["RUL_Hours"].to_numpy()
        inside = (true >= lo) & (true <= hi)
        alert_result = rul_alert_eval(prognostic, test, alert)
        rows.append(
            {
                "segmen_uji": k,
                **rul_metrics(true, pred),
                "mae_degradasi_tanpa_override": rul_metrics(true, prognostic)["mae_degradasi"],
                "cakupan_interval": round(float(inside.mean()), 4),
                "cakupan_degradasi": round(float(inside[true < RUL_CAP].mean()), 4) if (true < RUL_CAP).any() else np.nan,
                "lebar_interval_median": round(float(np.median(hi - lo)), 2),
                "ambang_alarm_jam": alert,
                "terdeteksi_sebelum_failure": alert_result["terdeteksi_sebelum_failure"],
                "lead_time_jam": None if pd.isna(alert_result["lead_time_jam"]) else round(alert_result["lead_time_jam"], 2),
                "alarm_rul_palsu": alert_result["alarm_palsu"],
                "bulan_uji": round((test.index.max() - test.index.min()).total_seconds() / (30 * 86400), 2),
            }
        )
        preds.append(pd.DataFrame({"rul_prognostik": prognostic, "rul_pred": pred, "rul_bawah": lo, "rul_atas": hi, "rul_ambang": alert}, index=test.index))
        validation = f"expanding-window segmen 1-{len(segments)}" if len(segments) >= 2 else "expanding-window 4 blok waktu di segmen 1"
        choices.append({"segmen_uji": k, "model": f"xgb_{name}", "ambang": alert, "validasi_dalam": validation, **{f"dalam_skor_{n}": round(v, 2) for n, v in inner_scores.items()}})
        print(f"  RUL segmen {k}: {name}, alarm {alert} jam, {time.time() - t0:.0f} detik", flush=True)
    return pd.DataFrame(rows), pd.concat(preds).sort_index(), pd.DataFrame(choices)


# ---------------------------------------------------------------------------
# Target, model akhir, ekspor
# ---------------------------------------------------------------------------
def check_targets(values, brier_baseline):
    rows = []
    for area, label, op, target, key in TARGETS:
        value = values[key]
        if key == "brier":
            target = brier_baseline
        if op == ">=":
            ok = value >= target
        elif op == "<=":
            ok = value <= target
        else:
            ok = target[0] <= value <= target[1]
        rows.append({"area": area, "metrik": label, "target": f"{op} {target}" if op != "antara" else f"{target[0]}-{target[1]}", "hasil": round(value, 4) if isinstance(value, float) else value, "status": "LULUS" if ok else "TIDAK LULUS"})
    return pd.DataFrame(rows)


def train_final_models(train_table, seed, cost_ratio):
    """Model untuk data sesudah Agustus 2020, dilatih dengan semua data berlabel. Kinerjanya = angka walk-forward."""
    cut = train_table.index.max() + pd.Timedelta(minutes=1)
    X, y, n_events = anomaly_train_rows(train_table, cut)
    name, info = inner_anomaly(X, y, X.index, EVENTS, seed, cost_ratio)
    members = fit_members(name, X, y, seed)

    segments = [1, 2, 3, 4]
    rul_name, rul_iso, conformal, alert, _ = inner_rul(train_table, segments, seed, cost_ratio)
    rul_model = fit_rul(RUL_CANDIDATES[rul_name], rul_rows(train_table, segments + [5], HEALTHY_STEP), seed)

    # IsolationForest dilatih ulang dengan resep yang sama seperti train_hybrid.train_final (60 hari normal terakhir),
    # supaya bundel tidak bergantung pada versi scikit-learn yang dipakai saat hybrid_final.joblib dibuat.
    normal = hybrid_normal_rows(train_table, "16")
    window = normal[normal.index >= normal.index.max() - pd.Timedelta(days=TRAIN_DAYS)]
    medians = window.median()
    iforest, if_threshold = fit_iforest(window.fillna(medians).to_numpy("float32"), seed)
    bundle = {
        "iforest": iforest,
        "if_threshold": float(if_threshold),
        "if_features": FEATURES,
        "medians": medians,
        "anomaly_members": members,  # Daftar (model, imputer). Skor = rata-rata predict_proba anggota.
        "anomaly_member_names": candidate_members(name),
        "anomaly_candidate": name,
        "anomaly_calibrator": info["iso"],
        "anomaly_threshold": float(info["threshold"]),
        "anomaly_features": FEATURES,
        "rul_model": rul_model,
        "rul_candidate": rul_name,
        "rul_isotonic": rul_iso,
        "rul_features": FEATURES,
        "rul_conformal": conformal,
        "rul_conformal_bins": CONFORMAL_BINS,
        "rul_alert_hours": float(alert),
        "rul_cap": RUL_CAP,
        "n_events": n_events,
        "seed": seed,
        "cost_ratio": cost_ratio,
    }
    joblib.dump(bundle, FINAL_DIR / "model_final.joblib", compress=3)
    for member_name, (model, _) in zip(candidate_members(name), members):
        if ANOMALY_CANDIDATES[member_name][0] == "xgb":
            model.save_model(FINAL_DIR / f"anomali_{member_name}.json")
    rul_model.save_model(FINAL_DIR / "rul_xgb.json")
    return bundle


def main():
    parser = argparse.ArgumentParser(description="Model final terkalibrasi untuk RUL dan anomali")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--cost-ratio", type=float, default=10.0, help="biaya kejadian terlewat dibanding satu alarm palsu")
    args = parser.parse_args()
    ensure_dirs()

    train_table, online_table = load_tables()
    test = anomaly_test_rows(online_table)

    print("Anomali, walk-forward dengan validasi dalam:")
    scores, anomaly_choices = anomaly_walk_forward(train_table, test, args.seed, args.cost_ratio)
    later = scores[scores.index >= MAY]

    baseline = pd.read_csv(MODEL_DIR / "baseline_anomali.csv")
    brier_baseline = float(baseline.loc[baseline["model"] == "XGBoost", "brier"].iloc[0])

    old, new = hybrid_frames(scores)
    raw_metrics = row_metrics(later["p_raw"], 0.5)
    # Ambang berbeda per bulan: precision/recall dari keputusan 0/1, metrik peluang dari skor terkalibrasi.
    decisions = row_metrics((later["p_cal"] > later["thr"]).astype(float), 0.5)
    probabilities = row_metrics(later["p_cal"], 0.5)
    cal_metrics = {**decisions, **{k: probabilities[k] for k in ("roc_auc", "pr_auc", "brier")}}
    reliability_raw, ece_raw = calibration_table(later["p_raw"])
    reliability_cal, ece_cal = calibration_table(later["p_cal"])

    anomaly_rows = [
        {**summarize_alarm("Model terpilih, skor mentah (ambang 0,5)", persist_alarm(scores["p_raw"] > 0.5)), **{k: raw_metrics[k] for k in ("precision_baris", "recall_baris", "f1_baris", "pr_auc", "brier")}, "ece": round(ece_raw, 4)},
        {**summarize_alarm("Model final terkalibrasi (ambang teroptimasi)", persist_alarm(scores["p_cal"] > scores["thr"])), **{k: cal_metrics[k] for k in ("precision_baris", "recall_baris", "f1_baris", "pr_auc", "brier")}, "ece": round(ece_cal, 4)},
        summarize_alarm("Hybrid lama Merah (HGB 0,5)", red_alarm(old)),
        summarize_alarm("Hybrid lama Kuning atau Merah", warning_alarm(old)),
        summarize_alarm("Hybrid final Merah", red_alarm(new)),
        summarize_alarm("Hybrid final Kuning atau Merah", warning_alarm(new)),
    ]
    anomaly = pd.DataFrame(anomaly_rows)

    print("RUL, walk-forward per segmen dengan validasi dalam:")
    rul_segments, rul_preds, rul_choices = rul_walk_forward(train_table, online_table, persist_alarm(scores["p_cal"] > scores["thr"]), args.seed, args.cost_ratio)
    true = online_table.loc[rul_preds.index, "RUL_Hours"].to_numpy()
    rul_overall = rul_metrics(true, rul_preds["rul_pred"])
    prognostic_only = rul_metrics(true, rul_preds["rul_prognostik"])
    rul_overall.update({f"{k}_tanpa_override": prognostic_only[k] for k in ("mae_semua", "mae_degradasi", "f1_makro_stage", "recall_critical")})
    rul_overall["cakupan_interval"] = round(float(np.mean((true >= rul_preds["rul_bawah"]) & (true <= rul_preds["rul_atas"]))), 4)
    with_failure = rul_segments[rul_segments["segmen_uji"] <= 4]
    rul_overall["failure_terdeteksi"] = int(with_failure["terdeteksi_sebelum_failure"].fillna(False).astype(bool).sum())
    rul_overall["lead_time_median_jam"] = float(with_failure["lead_time_jam"].dropna().median()) if with_failure["lead_time_jam"].notna().any() else np.nan
    rul_overall["alarm_rul_palsu_total"] = int(rul_segments["alarm_rul_palsu"].sum())
    rul_overall["alarm_rul_palsu_per_bulan"] = round(rul_overall["alarm_rul_palsu_total"] / rul_segments["bulan_uji"].sum(), 3)

    final_red = anomaly.set_index("metode").loc["Hybrid final Merah"]
    inside_all = (true >= rul_preds["rul_bawah"]) & (true <= rul_preds["rul_atas"])
    pre = (true > 0) & (true < RUL_CAP)
    rul_overall["cakupan_pra_failure"] = round(float(np.mean(inside_all[pre])), 4)
    values = {
        "kejadian": int(final_red["kejadian"].split("/")[0]),
        "resmi": int(final_red["resmi"].split("/")[0]),
        "palsu_per_minggu": float(final_red["palsu_per_minggu"]),
        "brier": float(cal_metrics["brier"]),
        "ece": float(ece_cal),
        "mae_semua": float(rul_overall["mae_semua"]),
        "cakupan": float(rul_overall["cakupan_pra_failure"]),
        "terdeteksi": rul_overall["failure_terdeteksi"],
        "palsu_per_bulan": float(rul_overall["alarm_rul_palsu_per_bulan"]),
        "mae_pra": float(rul_overall["mae_pra_failure"]),
    }
    targets = check_targets(values, brier_baseline)

    # Status per menit untuk analisis dan replay dashboard.
    status = new[["status", "pemicu"]].rename(columns={"status": "status_final", "pemicu": "pemicu_final"})
    status["status_lama"] = old["status"]
    prediction = pd.concat([scores.rename(columns={"p_raw": "p_xgb_mentah", "p_cal": "p_terkalibrasi", "thr": "ambang_anomali", "aktif": "model_aktif"}), status], axis=1)
    prediction = prediction.join(rul_preds, how="left")
    prediction.index.name = "timestamp"

    anomaly.to_csv(MODEL_DIR / "final_anomali.csv", index=False)
    rul_segments.to_csv(MODEL_DIR / "final_rul_per_segmen.csv", index=False)
    pd.DataFrame([rul_overall]).to_csv(MODEL_DIR / "final_rul.csv", index=False)
    targets.to_csv(MODEL_DIR / "final_target.csv", index=False)
    pd.concat([anomaly_choices.assign(bagian="anomali"), rul_choices.assign(bagian="RUL")], ignore_index=True).to_csv(MODEL_DIR / "final_pilihan_per_putaran.csv", index=False)
    reliability = pd.concat([reliability_raw.assign(skor="mentah"), reliability_cal.assign(skor="terkalibrasi")])
    reliability.to_csv(MODEL_DIR / "final_reliabilitas.csv", index=False)
    prediction.to_parquet(MODEL_DIR / "prediksi_walkforward.parquet")

    print("Model akhir untuk data baru:")
    bundle = train_final_models(train_table, args.seed, args.cost_ratio)
    save_json(
        {
            "dibuat": pd.Timestamp.now().isoformat(timespec="seconds"),
            "data_latih": [str(train_table.index.min()), str(train_table.index.max())],
            "catatan": "Model akhir dilatih dengan seluruh data Feb-Agu 2020. Kinerjanya diwakili angka walk-forward di bawah, bukan diukur ulang.",
            "anomali": {
                "model": bundle["anomaly_candidate"],
                "kalibrasi": "isotonic dari skor out-of-fold (GroupKFold per kelompok kejadian)",
                "ambang_terkalibrasi": bundle["anomaly_threshold"],
                "fitur": FEATURES,
                "if_threshold": bundle["if_threshold"],
            },
            "rul": {
                "model": f"XGBoost {bundle['rul_candidate']}",
                "batas_rul_jam": RUL_CAP,
                "ambang_alarm_jam": bundle["rul_alert_hours"],
                "interval": f"conformal Mondrian {int(COVERAGE * 100)}%",
                "conformal_rentang": list(CONFORMAL_BINS),
                "conformal_kuantil": {str(k): v for k, v in bundle["rul_conformal"].items()},
            },
            "cost_ratio": args.cost_ratio,
            "walk_forward": {"anomali": anomaly.to_dict("records"), "rul": rul_overall, "target": targets.to_dict("records")},
            "versi": {"python": platform.python_version(), "scikit-learn": sklearn.__version__, "xgboost": xgboost.__version__, "pandas": pd.__version__, "numpy": np.__version__},
        },
        FINAL_DIR / "metadata.json",
    )

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print("\nPilihan per putaran:")
    print(anomaly_choices.to_string(index=False))
    print(rul_choices.to_string(index=False))
    print("\nANOMALI (walk-forward April-Agustus)")
    print(anomaly.to_string(index=False))
    print(f"\nECE mentah {ece_raw:.4f}, terkalibrasi {ece_cal:.4f}")
    print("\nRUL per segmen")
    print(rul_segments.to_string(index=False))
    print("\nRUL gabungan:", rul_overall)
    print("\nTARGET")
    print(targets.to_string(index=False))
    print(f"\nModel akhir: anomali {bundle['anomaly_candidate']} ambang {bundle['anomaly_threshold']}, RUL {bundle['rul_candidate']} alarm {bundle['rul_alert_hours']} jam")


if __name__ == "__main__":
    main()
