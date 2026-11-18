"""
Model baseline RUL dan anomali (Random Forest dan XGBoost) dengan metrik evaluasi awal.

Jalankan:  python -m anomaly_detection.rul_final.train_baseline
Pilihan:   --seed 42  --alert-hours 24
Hasil:     output/model/
             baseline_anomali.csv           ringkasan per model (per kejadian dan per baris)
             baseline_anomali_per_bulan.csv metrik per putaran walk-forward
             baseline_rul.csv               ringkasan per model dan skema
             baseline_rul_per_segmen.csv    metrik per segmen uji
             baseline_metrik.json           semua angka di atas dalam satu berkas

Baseline sengaja tanpa penyetelan: hiperparameter bawaan, ambang anomali 0,5, ambang alarm RUL 24 jam.
Angka ini menjadi titik awal yang harus dikalahkan oleh model final (train_final_calibrated.py).

Anomali
  Target  : menit di dalam 16 kejadian Tabel II (Event_Flag), fitur 51 kolom dari preprocess_dataprep.py.
  Validasi: walk-forward per bulan April-Agustus, sama dengan sistem hybrid. April belum punya label, jadi tanpa model.
  Metrik  : kejadian terdeteksi, alarm palsu (episode), delay, precision/recall/F1 per baris, ROC-AUC, PR-AUC, Brier.

RUL
  Target  : RUL_Hours (jam menuju awal failure resmi berikutnya, dibatasi 72 jam).
  Validasi: walk-forward per segmen. Segmen k (periode menuju failure k) diuji oleh model yang hanya melihat segmen < k.
            Segmen 5 (sesudah F4, tanpa failure) dipakai untuk menghitung alarm RUL palsu.
            Skema LOFO (leave-one-failure-out, boleh melihat masa depan) dilaporkan sebagai batas atas, bukan hasil utama.
  Metrik  : MAE/RMSE (semua dan jendela degradasi < 72 jam), skor NASA PHM08, akurasi dan F1 stage, lead time alarm.
"""
import argparse
import time

import numpy as np
import pandas as pd

from anomaly_detection.common.model_utils import (
    MODEL_DIR,
    FEATURES,
    FOLDS,
    HEALTHY_STEP,
    RUL_CAP,
    RUL_TEST_SEGMENTS,
    SEED,
    MedianImputer,
    anomaly_test_rows,
    anomaly_train_rows,
    ensure_dirs,
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
from anomaly_detection.preprocessing.preprocess_iforest import EVENTS

MODELS = {"rf": "RandomForest", "xgb": "XGBoost"}
ANOMALY_THRESHOLD = 0.5
MAY = pd.Timestamp("2020-05-01")


# ---------------------------------------------------------------------------
# Anomali
# ---------------------------------------------------------------------------
def fit_classifier(kind, X, y, seed, **params):
    X = X.to_numpy("float32")
    imputer = MedianImputer().fit(X) if needs_imputer(kind) else None
    if imputer is not None:
        X = imputer.transform(X)
    if kind == "xgb":
        params.setdefault("scale_pos_weight", float((y == 0).sum() / max((y == 1).sum(), 1)))
    model = make_classifier(kind, seed, **params)
    ms = model.get_params().get("max_samples")
    if ms is not None and ms > len(X):
        model.set_params(max_samples=None)
    model = model.fit(X, y)
    return model, imputer


def predict_proba(model, imputer, X):
    X = X.to_numpy("float32")
    if imputer is not None:
        X = imputer.transform(X)
    return model.predict_proba(X)[:, 1]


def anomaly_walk_forward(train_table, test, kind, seed=SEED, **params):
    """Skor per menit April-Agustus. Bulan tanpa kejadian yang sudah diketahui mendapat skor 0 (kejadiannya terlewat)."""
    parts, info = [], []
    for start, end in FOLDS:
        X, y, n_events = anomaly_train_rows(train_table, start)
        fold_test = test[(test.index >= start) & (test.index < end)]
        if n_events == 0:
            proba = np.zeros(len(fold_test))
        else:
            model, imputer = fit_classifier(kind, X, y, seed, **params)
            proba = predict_proba(model, imputer, fold_test)
        parts.append(pd.Series(proba, index=fold_test.index))
        info.append({"bulan": f"{start:%b}", "baris_latih": len(X), "kejadian_diketahui": n_events})
    return pd.concat(parts).sort_index(), info


def anomaly_summary(name, scores, threshold):
    alarm = persist_alarm(scores > threshold)
    result = evaluate(to_episodes(alarm))
    first = result["first_alarm"]
    official = EVENTS.loc[EVENTS["official"], "id"]
    later = EVENTS.loc[EVENTS["start"] >= MAY, "id"]
    row = {
        "model": name,
        "ambang": threshold,
        "kejadian": f"{result['hits']}/{len(EVENTS)}",
        "resmi": f"{sum(first[i] is not None for i in official)}/{len(official)}",
        "mei_agu": f"{sum(first[i] is not None for i in later)}/{len(later)}",
        "alarm_palsu": len(result["false_alarms"]),
        "alarm_palsu_per_minggu": round(len(result["false_alarms"]) / TEST_WEEKS, 2),
        "precision_kejadian": round(result["precision"], 3),
        "recall_kejadian": round(result["recall"], 3),
        "f1_kejadian": round(result["f1"], 3),
        "delay_median_menit": result["median_delay"],
        "meleset": ",".join(k for k, t in first.items() if t is None),
    }
    # Metrik per baris hanya untuk Mei-Agustus: April tidak punya model supervised, jadi skornya nol semua.
    row.update(row_metrics(scores[scores.index >= MAY], threshold))
    return row


def anomaly_per_month(name, scores, threshold):
    rows = []
    for start, end in FOLDS[1:]:
        part = scores[(scores.index >= start) & (scores.index < end)]
        m = row_metrics(part, threshold)
        rows.append({"model": name, "bulan": f"{start:%b}", **{k: m[k] for k in ("precision_baris", "recall_baris", "f1_baris", "roc_auc", "pr_auc")}})
    return rows


# ---------------------------------------------------------------------------
# RUL
# ---------------------------------------------------------------------------
def fit_regressor(kind, X, y, seed, **params):
    X = X.to_numpy("float32")
    imputer = MedianImputer().fit(X) if needs_imputer(kind) else None
    if imputer is not None:
        X = imputer.transform(X)
    model = make_regressor(kind, seed, **params)
    ms = model.get_params().get("max_samples")
    if ms is not None and ms > len(X):
        model.set_params(max_samples=None)
    return model.fit(X, y), imputer


def predict_rul(model, imputer, X):
    X = X.to_numpy("float32")
    if imputer is not None:
        X = imputer.transform(X)
    return np.clip(model.predict(X), 0, RUL_CAP)


def rul_evaluate(train_table, online_table, kind, scheme="walk", seed=SEED, alert_hours=24.0, **params):
    """Satu baris metrik per segmen uji, plus prediksi per menit (Series)."""
    rows, preds = [], []
    test_segments = RUL_TEST_SEGMENTS if scheme == "walk" else (1, 2, 3, 4)
    for k in test_segments:
        train_segments = list(range(1, k)) if scheme == "walk" else [s for s in (1, 2, 3, 4) if s != k]
        train = rul_rows(train_table, train_segments, HEALTHY_STEP)
        test = rul_rows(online_table, [k])
        model, imputer = fit_regressor(kind, train[FEATURES], train["RUL_Hours"].to_numpy(), seed, **params)
        pred = pd.Series(predict_rul(model, imputer, test[FEATURES]), index=test.index)
        smoothed = smooth_rul(pred).fillna(pred)
        metrics = rul_metrics(test["RUL_Hours"], smoothed)
        alert = rul_alert_eval(smoothed, test, alert_hours)
        rows.append(
            {
                "model": MODELS[kind],
                "skema": scheme,
                "segmen_uji": k,
                "segmen_latih": ",".join(map(str, train_segments)),
                "baris_latih": len(train),
                **metrics,
                "ambang_alarm_jam": alert_hours,
                "terdeteksi_sebelum_failure": alert["terdeteksi_sebelum_failure"],
                "lead_time_jam": None if pd.isna(alert["lead_time_jam"]) else round(alert["lead_time_jam"], 2),
                "alarm_rul_palsu": alert["alarm_palsu"],
            }
        )
        preds.append(smoothed.rename("rul_pred"))
    return pd.DataFrame(rows), pd.concat(preds).sort_index()


def rul_overall(per_segment, preds, online_table):
    """Gabungan semua segmen uji (bukan rata-rata per segmen), supaya segmen panjang berbobot sesuai jumlah barisnya."""
    true = online_table.loc[preds.index, "RUL_Hours"]
    with_failure = per_segment[per_segment["segmen_uji"] <= 4]
    m = rul_metrics(true, preds)
    m.update(
        {
            "failure_terdeteksi": f"{int(with_failure['terdeteksi_sebelum_failure'].fillna(False).sum())}/{len(with_failure)}",
            "lead_time_median_jam": float(with_failure["lead_time_jam"].dropna().median()) if with_failure["lead_time_jam"].notna().any() else np.nan,
            "alarm_rul_palsu_total": int(per_segment["alarm_rul_palsu"].sum()),
        }
    )
    return m


def main():
    parser = argparse.ArgumentParser(description="Model baseline RUL dan anomali (RF dan XGBoost)")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--alert-hours", type=float, default=24.0)
    args = parser.parse_args()
    ensure_dirs()

    train_table, online_table = load_tables()
    test = anomaly_test_rows(online_table)

    anomaly_rows, monthly_rows, fold_info = [], [], {}
    for kind, name in MODELS.items():
        t0 = time.time()
        scores, info = anomaly_walk_forward(train_table, test, kind, args.seed)
        anomaly_rows.append(anomaly_summary(name, scores, ANOMALY_THRESHOLD))
        monthly_rows += anomaly_per_month(name, scores, ANOMALY_THRESHOLD)
        fold_info[name] = info
        print(f"anomali {name}: selesai {time.time() - t0:.0f} detik", flush=True)
    anomaly = pd.DataFrame(anomaly_rows)
    monthly = pd.DataFrame(monthly_rows)

    rul_segment_tables, rul_summary = [], []
    for kind, name in MODELS.items():
        for scheme in ("walk", "lofo"):
            t0 = time.time()
            per_segment, preds = rul_evaluate(train_table, online_table, kind, scheme, args.seed, args.alert_hours)
            rul_segment_tables.append(per_segment)
            rul_summary.append({"model": name, "skema": scheme, **rul_overall(per_segment, preds, online_table)})
            print(f"RUL {name} {scheme}: selesai {time.time() - t0:.0f} detik", flush=True)
    rul_segments = pd.concat(rul_segment_tables, ignore_index=True)
    rul = pd.DataFrame(rul_summary)

    anomaly.to_csv(MODEL_DIR / "baseline_anomali.csv", index=False)
    monthly.to_csv(MODEL_DIR / "baseline_anomali_per_bulan.csv", index=False)
    rul.to_csv(MODEL_DIR / "baseline_rul.csv", index=False)
    rul_segments.to_csv(MODEL_DIR / "baseline_rul_per_segmen.csv", index=False)
    save_json(
        {
            "catatan": "Baseline tanpa penyetelan. Anomali: walk-forward Apr-Agu, ambang 0,5. RUL: walk-forward per segmen, alarm 24 jam.",
            "seed": args.seed,
            "anomali": anomaly.to_dict("records"),
            "anomali_per_bulan": monthly.to_dict("records"),
            "anomali_info_putaran": fold_info,
            "rul": rul.to_dict("records"),
            "rul_per_segmen": rul_segments.to_dict("records"),
        },
        MODEL_DIR / "baseline_metrik.json",
    )

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print("\nANOMALI (walk-forward, ambang 0,5)")
    print(anomaly.to_string(index=False))
    print("\nRUL (gabungan segmen uji)")
    print(rul.to_string(index=False))
    print("\nRUL per segmen")
    print(rul_segments.drop(columns=["segmen_latih"]).to_string(index=False))


if __name__ == "__main__":
    main()
