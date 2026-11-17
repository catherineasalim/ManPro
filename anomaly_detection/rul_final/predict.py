"""
Memakai model final (output/model/final/model_final.joblib) pada data baru.

Jalankan:  python -m anomaly_detection.rul_final.predict   (dari root repo; contoh: menilai 7 hari terakhir tabel online)
Di kode :
    import joblib
    from anomaly_detection.rul_final.predict import score_table
    bundle = joblib.load("anomaly_detection/output/model/final/model_final.joblib")
    hasil = score_table(bundle, tabel_online_baru)   # kolom sama dengan hasil preprocess_dataprep.py

Keluaran per menit:
  status, pemicu        aturan hybrid yang sama (hybrid.combine_status), Merah dari model anomali terkalibrasi
  p_kejadian            skor terkalibrasi 0-1: perkiraan peluang menit ini bagian dari kejadian seperti 16 kejadian 2020
  rul_jam               perkiraan jam menuju kegagalan (maksimal 72), 0 jika pola kegagalan sedang berlangsung
  rul_bawah, rul_atas   interval 80% (conformal) dari validasi walk-forward
  rul_stage             Failure, Critical (<=6 jam), Warning (6-24 jam), Normal (>24 jam), atau Abu-abu
  rul_alarm             rul_jam di bawah ambang alarm teroptimasi (bukan saat Failure)

Jangan dipakai untuk memutar ulang Februari-Agustus 2020: model ini sudah melihat bulan-bulan itu.
Untuk replay jujur pakai output/model/prediksi_walkforward.parquet.
"""
import joblib
import numpy as np
import pandas as pd

from anomaly_detection.common.model_utils import FINAL_DIR, RUL_CAP, load_tables, smooth_rul
from anomaly_detection.common.evaluation import persist_alarm
from anomaly_detection.common.hybrid import GREY, combine_status, to_grid

BUNDLE_PATH = FINAL_DIR / "model_final.joblib"


def anomaly_probability(bundle, rows):
    X = rows[bundle["anomaly_features"]].to_numpy("float32")
    raw = []
    for model, imputer in bundle["anomaly_members"]:
        Xm = imputer.transform(X) if imputer is not None else X
        raw.append(model.predict_proba(Xm)[:, 1])
    raw = np.mean(raw, axis=0)
    calibrator = bundle["anomaly_calibrator"]
    return raw if calibrator is None else calibrator.predict(raw)


def rul_estimate(bundle, rows, failing):
    raw = pd.Series(np.clip(bundle["rul_model"].predict(rows[bundle["rul_features"]].to_numpy("float32")), 0, RUL_CAP), index=rows.index)
    raw = smooth_rul(raw).fillna(raw)
    prognostic = pd.Series(bundle["rul_isotonic"].predict(raw.to_numpy()), index=rows.index)
    pred = prognostic.where(~failing, 0.0)
    bins = np.clip(np.digitize(pred.to_numpy(), bundle["rul_conformal_bins"][1:-1]), 0, len(bundle["rul_conformal_bins"]) - 2)
    point = pred.to_numpy()
    lo = np.clip(np.minimum(point + np.array([bundle["rul_conformal"][b][0] for b in bins]), point), 0, RUL_CAP)
    hi = np.clip(np.maximum(point + np.array([bundle["rul_conformal"][b][1] for b in bins]), point), 0, RUL_CAP)
    return prognostic, pred, lo, hi


def score_table(bundle, table):
    rows = table[table["data_ok"]]
    if_input = rows[bundle["if_features"]].fillna(bundle["medians"]).to_numpy("float32")
    p = anomaly_probability(bundle, rows)
    scored = pd.DataFrame(
        {
            "if_score": -bundle["iforest"].score_samples(if_input),
            "if_threshold": bundle["if_threshold"],
            "hgb_score": p,
            "hgb_threshold": bundle["anomaly_threshold"],
            "hgb_aktif": True,
        },
        index=rows.index,
    )
    status = to_grid(combine_status(scored), table.index)

    failing = persist_alarm(pd.Series(p > bundle["anomaly_threshold"], index=rows.index))
    prognostic, pred, lo, hi = rul_estimate(bundle, rows, failing.to_numpy())
    out = status[["status", "pemicu"]].copy()
    out["p_kejadian"] = pd.Series(p, index=rows.index).reindex(table.index)
    out["rul_jam"] = pred.reindex(table.index)
    out["rul_bawah"] = pd.Series(lo, index=rows.index).reindex(table.index)
    out["rul_atas"] = pd.Series(hi, index=rows.index).reindex(table.index)
    stage = np.select(
        [out["rul_jam"].isna(), failing.reindex(table.index).fillna(False).to_numpy(bool), out["rul_jam"] <= 6, out["rul_jam"] <= 24],
        [GREY, "Failure", "Critical", "Warning"],
        "Normal",
    )
    out["rul_stage"] = stage
    out["rul_alarm"] = (prognostic.reindex(table.index) < bundle["rul_alert_hours"]).fillna(False) & (out["rul_stage"] != "Failure")
    return out


def main():
    bundle = joblib.load(BUNDLE_PATH)
    _, online = load_tables()
    recent = online[online.index >= online.index.max() - pd.Timedelta(days=7)]
    result = score_table(bundle, recent)
    print(f"Contoh 7 hari terakhir ({recent.index.min():%d %b} - {recent.index.max():%d %b %Y}). Data ini sudah dilihat model, jadi hanya uji teknis.")
    print("Status:", result["status"].value_counts().to_dict())
    print("Stage RUL:", result["rul_stage"].value_counts().to_dict())
    print(result.dropna().tail(5).to_string())


if __name__ == "__main__":
    main()
