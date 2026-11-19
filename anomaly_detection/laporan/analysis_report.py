"""
Laporan analisis dan insight proyek.

Jalankan:  python -m anomaly_detection.laporan.analysis_report        (sesudah train_baseline.py dan train_final_calibrated.py)
Hasil:     output/model/LAPORAN_ANALISIS.md   laporan lengkap (tabel dan grafik)
           output/model/grafik/*.png          9 grafik
           output/model/analisis_*.csv        tabel pendukung (FP, FN, ROI, sensitivitas, degradasi)

Isi
  1. Ringkasan model: baseline vs final, pemeriksaan target
  2. Analisis FP/FN: setiap alarm palsu Merah dan kejadian terlewat, dengan konteks sensor dan kategori penyebab
  3. Simulasi ROI dengan batas rendah, nilai dasar, dan batas tinggi UB sesuai tabel asumsi biaya
  4. Analisis sensitivitas: tornado parameter ROI, titik impas, dan kurva ambang
  5. Insight pola degradasi: lintasan sensor menjelang 4 kegagalan, kejadian prekursor, fitur penting

Angka kinerja yang dipakai ROI berasal dari status sistem hybrid final pada validasi walk-forward
(kolom status_final di output/model/prediksi_walkforward.parquet), bukan dari model yang dilatih ulang pada seluruh data.
"""
import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from anomaly_detection.common.model_utils import MODEL_DIR, OUTPUT_DIR, CHART_DIR, COLORS, FEATURES, FINAL_DIR, RUL_CAP, ensure_dirs, load_tables, row_labels
from anomaly_detection.common.evaluation import TEST_WEEKS, evaluate, persist_alarm, to_episodes
from anomaly_detection.preprocessing.preprocess_dataprep import FAILURES
from anomaly_detection.preprocessing.preprocess_iforest import EVENTS, MAINTENANCE_GAPS, MARGIN

MAY = pd.Timestamp("2020-05-01")
LABELED_MONTHS = 4.0  # April-Juli: periode 16 kejadian diberi label.
OBSERVED_MONTHS = 7.0  # Februari-Agustus: periode 4 kegagalan resmi.
# ---------------------------------------------------------------------------
# Nilai biaya mengikuti tabel asumsi UB pada milestone.
# ---------------------------------------------------------------------------
FAILURES_PER_UNIT_YEAR = len(FAILURES) / OBSERVED_MONTHS * 12
DOWNTIME_HOURS_PER_FAILURE = (
    (FAILURES["end"] - FAILURES["start"]).dt.total_seconds().mean() / 3600
)
ROI_SCENARIOS = {
    "Batas rendah": {
        "kegagalan_per_unit_tahun": FAILURES_PER_UNIT_YEAR,
        "downtime_jam_per_kegagalan": DOWNTIME_HOURS_PER_FAILURE,
        "biaya_downtime_per_jam": 0.2,
        "biaya_perbaikan_darurat": 2,
        "biaya_perbaikan_terencana": 0.8,
        "biaya_inspeksi": 0.05,
        "interval_penggantian_bulan": 12,
        "biaya_penggantian_preventif": 1,
        "kegagalan_lolos_preventif": 0.1,
        "biaya_sistem": 0.5,
    },
    "Dasar": {
        "kegagalan_per_unit_tahun": FAILURES_PER_UNIT_YEAR,
        "downtime_jam_per_kegagalan": DOWNTIME_HOURS_PER_FAILURE,
        "biaya_downtime_per_jam": 0.5,
        "biaya_perbaikan_darurat": 3,
        "biaya_perbaikan_terencana": 1,
        "biaya_inspeksi": 0.1,
        "interval_penggantian_bulan": 6,
        "biaya_penggantian_preventif": 1.2,
        "kegagalan_lolos_preventif": 0.3,
        "biaya_sistem": 1,
    },
    "Batas tinggi": {
        "kegagalan_per_unit_tahun": FAILURES_PER_UNIT_YEAR,
        "downtime_jam_per_kegagalan": DOWNTIME_HOURS_PER_FAILURE,
        "biaya_downtime_per_jam": 1.5,
        "biaya_perbaikan_darurat": 5,
        "biaya_perbaikan_terencana": 1.5,
        "biaya_inspeksi": 0.2,
        "interval_penggantian_bulan": 3,
        "biaya_penggantian_preventif": 2,
        "kegagalan_lolos_preventif": 0.6,
        "biaya_sistem": 3,
    },
}
PARAM_LABELS = {
    "kegagalan_per_unit_tahun": "Kegagalan besar per unit per tahun",
    "downtime_jam_per_kegagalan": "Downtime per kegagalan (jam)",
    "biaya_downtime_per_jam": "Biaya downtime per jam (UB/jam)",
    "biaya_perbaikan_darurat": "Biaya perbaikan darurat (UB)",
    "biaya_perbaikan_terencana": "Biaya perbaikan terencana prediktif (UB)",
    "biaya_inspeksi": "Biaya inspeksi per alarm palsu (UB)",
    "interval_penggantian_bulan": "Interval penggantian terjadwal (bulan)",
    "biaya_penggantian_preventif": "Biaya penggantian terjadwal (UB/penggantian)",
    "kegagalan_lolos_preventif": "Kegagalan yang lolos di preventif",
    "biaya_sistem": "Biaya sistem prediktif (UB/tahun)",
    "recall_resmi": "Recall kegagalan resmi",
    "alarm_palsu_per_minggu": "Alarm Merah tanpa kegagalan resmi per minggu",
}
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e6e5e0", "grid.linewidth": 0.6, "axes.edgecolor": "#8a8984", "axes.titleweight": "bold", "axes.titlesize": 10})


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------
def num(v, digits=2):
    """Format angka Indonesia: titik pemisah ribuan, koma desimal."""
    if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)):
        return "-"
    text = f"{v:,.{digits}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def md_table(df, floatfmt=2):
    def fmt(v):
        if isinstance(v, (bool, np.bool_)):
            return "Ya" if v else "Tidak"
        if isinstance(v, (float, np.floating)):
            return num(v, floatfmt)
        if isinstance(v, (int, np.integer)):
            return num(v, 0)
        if isinstance(v, pd.Timestamp):
            return f"{v:%d %b %Y %H:%M}"
        return str(v)

    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def ub(v, digits=2):
    sign = "-" if v < 0 else ""
    return f"{sign}{num(abs(v), digits)} UB"


METHOD_NAMES = {
    "RandomForest baseline (0,5)": "Baseline Random Forest",
    "XGBoost baseline (0,5)": "Baseline XGBoost",
    "Model final terkalibrasi (ambang teroptimasi)": "Model final terkalibrasi",
    "Hybrid lama Merah (HGB 0,5)": "Sistem hybrid versi awal, Merah",
    "Hybrid lama Kuning atau Merah": "Sistem hybrid versi awal, Kuning/Merah",
    "Hybrid final Merah": "Sistem hybrid final, Merah",
    "Hybrid final Kuning atau Merah": "Sistem hybrid final, Kuning/Merah",
}


def save(fig, name):
    fig.savefig(CHART_DIR / name, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return f"grafik/{name}"


# ---------------------------------------------------------------------------
# 1. Ringkasan model
# ---------------------------------------------------------------------------
def model_summary():
    base_a = pd.read_csv(MODEL_DIR / "baseline_anomali.csv")
    base_r = pd.read_csv(MODEL_DIR / "baseline_rul.csv")
    if "mae_pra_failure" not in base_r:
        base_r["mae_pra_failure"] = np.nan
    final_a = pd.read_csv(MODEL_DIR / "final_anomali.csv")
    final_r = pd.read_csv(MODEL_DIR / "final_rul.csv")
    targets = pd.read_csv(MODEL_DIR / "final_target.csv")
    choices = pd.read_csv(MODEL_DIR / "final_pilihan_per_putaran.csv")

    anomaly = pd.concat(
        [
            base_a.assign(metode=base_a["model"] + " baseline (0,5)")[["metode", "kejadian", "resmi", "alarm_palsu", "delay_median_menit", "f1_baris", "pr_auc", "brier"]],
            final_a[final_a["metode"].str.startswith(("Model final", "Hybrid"))][["metode", "kejadian", "resmi", "alarm_palsu", "delay_median_menit", "f1_baris", "pr_auc", "brier"]],
        ],
        ignore_index=True,
    )
    rul_cols = ["mae_semua", "mae_pra_failure", "mae_degradasi", "mae_kritis_24j", "nasa_skor_degradasi", "f1_makro_stage", "recall_critical"]
    rul = pd.concat(
        [
            base_r[base_r["skema"] == "walk"].assign(model=lambda d: d["model"] + " baseline")[["model"] + rul_cols + ["alarm_rul_palsu_total"]],
            final_r.assign(model="XGBoost final terkalibrasi + override Failure")[["model"] + rul_cols + ["alarm_rul_palsu_total"]],
        ],
        ignore_index=True,
    )

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    show = anomaly[anomaly["metode"].isin(["RandomForest baseline (0,5)", "XGBoost baseline (0,5)", "Model final terkalibrasi (ambang teroptimasi)", "Hybrid lama Merah (HGB 0,5)", "Hybrid final Merah"])]
    names = show["metode"].map(METHOD_NAMES).str.replace(", Merah", "", regex=False)
    hits = show["kejadian"].str.split("/").str[0].astype(int)
    colors = [COLORS["muted"], COLORS["muted"], COLORS["s1"], COLORS["muted"], COLORS["s1"]]
    axes[0].barh(names, hits, color=colors, height=0.55)
    axes[0].set_xlim(0, 16)
    axes[0].set_title("Kejadian terdeteksi (dari 16)")
    for y, v in enumerate(hits):
        axes[0].text(v + 0.2, y, str(v), va="center")
    axes[1].barh(names, show["alarm_palsu"], color=colors, height=0.55)
    axes[1].set_title("Alarm palsu (episode, Apr-Agu)")
    axes[1].set_yticklabels([])
    for y, v in enumerate(show["alarm_palsu"]):
        axes[1].text(v + 0.1, y, str(v), va="center")
    for ax in axes:
        ax.invert_yaxis()
        ax.grid(axis="y", visible=False)
    fig.suptitle("Walk-forward April-Agustus 2020: biru = model final", x=0.01, y=1.04, ha="left", fontsize=10)
    chart = save(fig, "01_baseline_vs_final.png")
    return anomaly, rul, targets, choices, chart


def reliability_chart():
    rel = pd.read_csv(MODEL_DIR / "final_reliabilitas.csv")
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot([0, 1], [0, 1], color=COLORS["muted"], linewidth=1, linestyle="--", label="Kalibrasi sempurna")
    for name, color in (("mentah", COLORS["s2"]), ("terkalibrasi", COLORS["s1"])):
        part = rel[(rel["skor"] == name) & (rel["n"] > 0)]
        ax.plot(part["rata_prediksi"], part["frekuensi_nyata"], marker="o", markersize=5, linewidth=2, color=color, label=f"Skor {name}")
    ax.set_xlabel("Rata-rata skor model")
    ax.set_ylabel("Porsi menit yang benar kejadian")
    ax.set_title("Reliabilitas skor anomali (Mei-Agu)")
    ax.legend(frameon=False, loc="upper left")
    return save(fig, "02_reliabilitas.png")


def rul_chart(pred, online):
    fig, axes = plt.subplots(3, 1, figsize=(10, 7.5), sharey=True)
    for ax, f in zip(axes, FAILURES[FAILURES["id"] > 1].itertuples()):  # F1 jatuh di segmen latih pertama, tanpa prediksi.
        window = pred[(pred.index >= f.start - pd.Timedelta(days=5)) & (pred.index <= f.end + pd.Timedelta(hours=6))]
        true = online.loc[window.index, "RUL_Hours"]
        ax.fill_between(window.index, window["rul_bawah"], window["rul_atas"], color=COLORS["s1"], alpha=0.15, linewidth=0, label="Interval 80%")
        ax.plot(true.index, true, color=COLORS["text"], linewidth=1.2, label="RUL sebenarnya")
        ax.plot(window.index, window["rul_prognostik"], color=COLORS["s2"], linewidth=1.2, label="Prognostik (regresi + isotonic)")
        ax.plot(window.index, window["rul_pred"], color=COLORS["s1"], linewidth=2, label="RUL final (dengan override Failure)")
        ax.set_title(f"F{f.id}: mulai {f.start:%d %b %H:%M}")
        ax.set_ylabel("Jam")
    axes[0].legend(frameon=False, ncol=4, loc="lower left", fontsize=8)
    fig.tight_layout()
    return save(fig, "03_rul_walkforward.png")


# ---------------------------------------------------------------------------
# 2. FP / FN
# ---------------------------------------------------------------------------
def nearest_event(a, b):
    best = None
    for e in EVENTS.itertuples():
        if b < e.start:
            gap = (e.start - b).total_seconds() / 3600
            side = "sebelum"
        elif a > e.end:
            gap = (a - e.end).total_seconds() / 3600
            side = "sesudah"
        else:
            gap, side = 0.0, "di dalam"
        if best is None or gap < best[1]:
            best = (e.id, gap, side)
    return best


def categorize_fp(row):
    if row["jarak_ke_kejadian_jam"] <= 6:
        return "Dekat batas kejadian berlabel (<= 6 jam)"
    if row["pola_kebocoran_tak_berlabel"]:
        return "Pola kebocoran tanpa label"
    if row["duty_60"] >= 0.5:
        return "Beban tinggi tanpa label"
    if row["sesudah_gap_data"]:
        return "Sesudah gap data"
    return "Lainnya"


def fp_table(alarm, rows, train_table, gaps, level):
    result = evaluate(to_episodes(alarm))
    records = []
    for a, b in result["false_alarms"]:
        event_id, gap, side = nearest_event(a, b)
        record = {
            "level": level,
            "mulai": a,
            "menit": int((b - a).total_seconds() / 60) + 1,
            "kejadian_terdekat": event_id,
            "posisi": side,
            "jarak_ke_kejadian_jam": round(gap, 1),
            "pola_kebocoran_tak_berlabel": bool(train_table["suspect"].reindex(pd.date_range(a, b, freq="1min")).fillna(False).any()),
            "sesudah_gap_data": bool((((a - gaps) >= pd.Timedelta(0)) & ((a - gaps) <= pd.Timedelta(hours=2))).any()),
        }
        for column in ("duty_60", "load_run_min", "oil_mean_15", "curr_mean_60", "tp2_mean_60"):
            record[column] = round(float(rows.loc[a, column]), 3) if a in rows.index else np.nan
        record["jam"] = a.hour
        records.append(record)
    table = pd.DataFrame(records)
    if len(table):
        table["kategori"] = table.apply(categorize_fp, axis=1)
    return table


def fn_table(pred, online):
    red = pred["status_final"] == "Merah"
    warning = pred["status_final"].isin(["Kuning", "Merah"])
    red_first = evaluate(to_episodes(red))["first_alarm"]
    warn_first = evaluate(to_episodes(warning))["first_alarm"]
    records = []
    for e in EVENTS.itertuples():
        window = pred[(pred.index >= e.start - MARGIN) & (pred.index <= e.end)]
        grid = online[(online.index >= e.start) & (online.index <= e.end)]
        records.append(
            {
                "kejadian": e.id,
                "resmi": e.official,
                "durasi_menit": int((e.end - e.start).total_seconds() / 60),
                "porsi_data_ok": round(float(grid["data_ok"].mean()), 2),
                "merah": red_first[e.id] is not None,
                "kuning_atau_merah": warn_first[e.id] is not None,
                "delay_merah_menit": (red_first[e.id] - e.start).total_seconds() / 60 if red_first[e.id] is not None else np.nan,
                "skor_maks": round(float(window["p_terkalibrasi"].max()), 3) if len(window) else np.nan,
                "model_aktif": bool(window["model_aktif"].any()) if len(window) else False,
                "duty_60_maks": round(float(online.loc[grid.index, "duty_60"].max()), 2),
                "load_run_maks": float(online.loc[grid.index, "load_run_min"].max()),
            }
        )
    table = pd.DataFrame(records)

    def reason(r):
        if r["merah"]:
            return "-"
        if not r["model_aktif"]:
            if r["durasi_menit"] < 60:
                return "April: model supervised belum ada, dan kejadian < 60 menit sehingga aturan cold start (IF 60 menit) tidak sempat menjadi Merah"
            return "April: model supervised belum ada"
        if r["porsi_data_ok"] < 0.5:
            return "Data sensor sebagian besar kosong"
        return "Skor di bawah ambang"

    table["penyebab_terlewat"] = table.apply(reason, axis=1)
    return table


def fp_chart(fp_red, fp_warn):
    order = ["Dekat batas kejadian berlabel (<= 6 jam)", "Pola kebocoran tanpa label", "Beban tinggi tanpa label", "Sesudah gap data", "Lainnya"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2), sharey=True)
    for ax, table, title, color in ((axes[0], fp_red, "Merah (notifikasi)", COLORS["s1"]), (axes[1], fp_warn, "Kuning atau Merah (dashboard)", COLORS["s2"])):
        counts = table["kategori"].value_counts().reindex(order).fillna(0).astype(int) if len(table) else pd.Series(0, index=order)
        ax.barh(order, counts.to_numpy(), color=color, height=0.55)
        for y, v in enumerate(counts.to_numpy()):
            ax.text(v + 0.2, y, str(v), va="center")
        ax.set_title(f"Alarm palsu {title}: {int(counts.sum())}")
        ax.invert_yaxis()
        ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return save(fig, "04_fp_kategori.png")


def confusion(pred):
    later = pred[pred.index >= MAY]
    y, neutral = row_labels(later.index)
    used = ~neutral
    decision = (later["p_terkalibrasi"] > later["ambang_anomali"]).to_numpy()[used]
    y = y[used]
    return pd.DataFrame(
        {"": ["Sebenarnya kejadian", "Sebenarnya normal"], "Prediksi kejadian": [int((decision & (y == 1)).sum()), int((decision & (y == 0)).sum())], "Prediksi normal": [int((~decision & (y == 1)).sum()), int((~decision & (y == 0)).sum())]}
    )


# ---------------------------------------------------------------------------
# 3-4. ROI dan sensitivitas
# ---------------------------------------------------------------------------
def official_alarm_metrics(alarm, weeks):
    episodes = to_episodes(alarm)
    official = EVENTS[
        EVENTS["official"]
        & (EVENTS["start"] >= alarm.index.min())
        & (EVENTS["start"] <= alarm.index.max())
    ]
    matched_episodes = set()
    detected = 0
    for event in official.itertuples():
        hits = [
            i for i, (start, end) in enumerate(episodes)
            if start <= event.end and end >= event.start - MARGIN
        ]
        if hits:
            detected += 1
            matched_episodes.add(hits[0])
    false_positives = sum(
        i not in matched_episodes
        and not any(start <= gap_end and end >= gap_start for gap_start, gap_end in MAINTENANCE_GAPS)
        for i, (start, end) in enumerate(episodes)
    )
    return {
        "recall_resmi": detected / len(official),
        "alarm_palsu_per_minggu": false_positives / weeks,
    }


def detection_inputs(hybrid_status):
    return official_alarm_metrics(hybrid_status == "Merah", TEST_WEEKS)


def roi(params, detection):
    p = {**params, **detection}
    failures = p["kegagalan_per_unit_tahun"]
    reactive_per_failure = (
        p["downtime_jam_per_kegagalan"] * p["biaya_downtime_per_jam"]
        + p["biaya_perbaikan_darurat"]
    )
    reactive_year = failures * reactive_per_failure

    preventive_replacements = 12 / p["interval_penggantian_bulan"]
    preventive_failures = failures * p["kegagalan_lolos_preventif"]
    preventive_year = (
        preventive_replacements * p["biaya_penggantian_preventif"]
        + preventive_failures * reactive_per_failure
    )

    true_positives = failures * p["recall_resmi"]
    false_negatives = failures - true_positives
    false_positives = p["alarm_palsu_per_minggu"] * 52
    planned_repairs = true_positives * p["biaya_perbaikan_terencana"]
    missed_failure_cost = false_negatives * reactive_per_failure
    inspection_cost = false_positives * p["biaya_inspeksi"]
    predictive_year = planned_repairs + missed_failure_cost + inspection_cost + p["biaya_sistem"]
    saving_vs_reactive = reactive_year - predictive_year
    saving_vs_preventive = preventive_year - predictive_year
    return {
        "biaya_reaktif_per_tahun": reactive_year,
        "biaya_preventif_per_tahun": preventive_year,
        "tp_per_tahun": true_positives,
        "fn_per_tahun": false_negatives,
        "fp_per_tahun": false_positives,
        "biaya_perbaikan_terencana_per_tahun": planned_repairs,
        "biaya_kegagalan_lolos_per_tahun": missed_failure_cost,
        "biaya_inspeksi_per_tahun": inspection_cost,
        "biaya_sistem_per_tahun": p["biaya_sistem"],
        "biaya_prediktif_per_tahun": predictive_year,
        "penghematan_vs_reaktif_per_tahun": saving_vs_reactive,
        "penghematan_vs_preventif_per_tahun": saving_vs_preventive,
        "roi_vs_reaktif_persen": saving_vs_reactive / p["biaya_sistem"] * 100,
        "roi_vs_preventif_persen": saving_vs_preventive / p["biaya_sistem"] * 100,
    }


def roi_tables(detection):
    rows = []
    for name, params in ROI_SCENARIOS.items():
        rows.append({"skenario": name, **roi(params, detection)})
    return pd.DataFrame(rows)


def tornado(detection, swing=0.3):
    base_params = ROI_SCENARIOS["Dasar"]
    base = roi(base_params, detection)["roi_vs_reaktif_persen"]
    rows = []
    keys = (
        "kegagalan_per_unit_tahun",
        "downtime_jam_per_kegagalan",
        "biaya_downtime_per_jam",
        "biaya_perbaikan_darurat",
        "biaya_perbaikan_terencana",
        "biaya_inspeksi",
        "biaya_sistem",
        "recall_resmi",
        "alarm_palsu_per_minggu",
    )
    for key in keys:
        values = []
        for factor in (1 - swing, 1 + swing):
            params, det = dict(base_params), dict(detection)
            if key in params:
                params[key] = params[key] * factor
                if key == "kegagalan_lolos_preventif":
                    params[key] = min(max(params[key], 0.0), 1.0)
            else:
                det[key] = min(det[key] * factor, 1.0) if key.startswith("recall") else det[key] * factor
            values.append(roi(params, det)["roi_vs_reaktif_persen"])
        rows.append({"parameter": PARAM_LABELS[key], "roi_turun_30": values[0], "roi_naik_30": values[1], "rentang": abs(values[1] - values[0])})
    return pd.DataFrame(rows).sort_values("rentang", ascending=False), base


def break_even(detection):
    """Nilai tiap parameter yang membuat ROI vs reaktif = 0, parameter lain tetap pada nilai dasar."""
    params = ROI_SCENARIOS["Dasar"]
    rows = []
    for key in ("recall_resmi", "alarm_palsu_per_minggu", "kegagalan_per_unit_tahun"):
        current = params[key] if key in params else detection[key]

        def f(value):
            p, d = (dict(params), dict(detection))
            (p if key in p else d)[key] = value
            return roi(p, d)["roi_vs_reaktif_persen"]

        lo, hi = 0.0, current * 50
        if key == "recall_resmi":
            hi = 1.0
        if np.sign(f(lo)) == np.sign(f(hi)):
            rows.append({"parameter": PARAM_LABELS[key], "nilai_dasar": current, "titik_impas": np.nan})
            continue
        rising = f(hi) > f(lo)
        for _ in range(80):
            mid = (lo + hi) / 2
            if (f(mid) < 0) == rising:
                lo = mid
            else:
                hi = mid
        rows.append({"parameter": PARAM_LABELS[key], "nilai_dasar": current, "titik_impas": round((lo + hi) / 2, 3), "arah": "minimal" if rising else "maksimal"})
    return pd.DataFrame(rows)


def threshold_curve(pred):
    """Ilustrasi saja: ambang diterapkan pada bulan uji yang sama. Tidak boleh dipakai untuk memilih ambang."""
    later = pred[pred["model_aktif"]]
    rows = []
    for thr in np.round(np.arange(0.1, 0.96, 0.05), 2):
        alarm = persist_alarm(later["p_terkalibrasi"] > thr)
        result = evaluate(to_episodes(alarm))
        later_events = EVENTS[EVENTS["start"] >= MAY]
        hit = {i: result["first_alarm"][i] is not None for i in later_events["id"]}
        official = later_events[later_events["official"]]["id"]
        minor = later_events[~later_events["official"]]["id"]
        rows.append(
            {
                "ambang": thr,
                "kejadian_mei_agu": sum(hit.values()),
                "recall_resmi": sum(hit[i] for i in official) / len(official),
                "recall_kecil": sum(hit[i] for i in minor) / len(minor),
                "alarm_palsu": len(result["false_alarms"]),
                "delay_median_menit": result["median_delay"],
            }
        )
    table = pd.DataFrame(rows)
    weeks_active = (later.index.max() - later.index.min()).total_seconds() / (7 * 86400)
    params = ROI_SCENARIOS["Dasar"]
    nets = []
    for r in table.itertuples():
        alarm = persist_alarm(later["p_terkalibrasi"] > r.ambang)
        det = official_alarm_metrics(alarm, weeks_active)
        nets.append(roi(params, det)["penghematan_vs_reaktif_per_tahun"])
    table["penghematan_vs_reaktif_per_tahun_dasar"] = nets
    return table


def roi_charts(roi_table, tornado_table, base_roi, curve, chosen_thresholds):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
    names = roi_table["skenario"]
    colors = [COLORS["s2"], COLORS["s1"], COLORS["s3"]]
    x = np.arange(len(names))
    width = 0.24
    for offset, key, label, color in (
        (-width, "biaya_reaktif_per_tahun", "Reaktif", COLORS["s2"]),
        (0, "biaya_preventif_per_tahun", "Preventif", COLORS["s1"]),
        (width, "biaya_prediktif_per_tahun", "Prediktif", COLORS["s3"]),
    ):
        axes[0].bar(x + offset, roi_table[key], width, label=label, color=color)
    axes[0].set_xticks(x, names)
    axes[0].set_ylabel("Biaya (UB/tahun)")
    axes[0].set_title("Biaya tahunan per strategi")
    axes[0].legend(frameon=False)
    axes[1].bar(x - width / 2, roi_table["roi_vs_reaktif_persen"], width, label="vs reaktif", color=COLORS["s2"])
    axes[1].bar(x + width / 2, roi_table["roi_vs_preventif_persen"], width, label="vs preventif", color=COLORS["s1"])
    axes[1].axhline(0, color=COLORS["text"], linewidth=0.8)
    axes[1].set_xticks(x, names)
    axes[1].set_title("ROI tahunan: penghematan / biaya sistem")
    axes[1].set_ylabel("ROI (%)")
    axes[1].legend(frameon=False)
    for ax in axes:
        ax.grid(axis="x", visible=False)
    fig.suptitle("Simulasi biaya dan ROI per unit APU (asumsi UB)", x=0.01, y=1.04, ha="left", fontsize=10)
    roi_chart = save(fig, "05_roi_skenario.png")

    fig, ax = plt.subplots(figsize=(8, 4.2))
    t = tornado_table.iloc[::-1]
    y = np.arange(len(t))
    ax.barh(y, t["roi_turun_30"] - base_roi, left=base_roi, color=COLORS["s2"], height=0.55, label="Parameter -30%")
    ax.barh(y, t["roi_naik_30"] - base_roi, left=base_roi, color=COLORS["s1"], height=0.55, label="Parameter +30%")
    ax.axvline(base_roi, color=COLORS["text"], linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(t["parameter"])
    ax.set_xlabel("ROI vs reaktif (%)")
    ax.set_title(f"Sensitivitas ROI pada nilai dasar ({base_roi:,.0f}%)")
    ax.legend(frameon=False, loc="lower right")
    ax.grid(axis="y", visible=False)
    tornado_chart = save(fig, "06_tornado_sensitivitas.png")

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.2), sharex=True)
    axes[0].plot(curve["ambang"], curve["kejadian_mei_agu"], color=COLORS["s1"], marker="o", markersize=4, linewidth=2)
    axes[0].set_title("Kejadian Mei-Agu terdeteksi (dari 12)")
    axes[1].plot(curve["ambang"], curve["alarm_palsu"], color=COLORS["s2"], marker="o", markersize=4, linewidth=2)
    axes[1].set_title("Alarm palsu (episode)")
    axes[2].plot(curve["ambang"], curve["penghematan_vs_reaktif_per_tahun_dasar"], color=COLORS["s3"], marker="o", markersize=4, linewidth=2)
    axes[2].set_title("Penghematan vs reaktif/tahun, dasar (UB)")
    for ax in axes:
        for thr in chosen_thresholds:
            ax.axvline(thr, color=COLORS["muted"], linewidth=0.8, linestyle=":")
        ax.set_xlabel("Ambang skor terkalibrasi")
    fig.suptitle("Sensitivitas ambang (ilustrasi pada data uji; garis titik = ambang yang dipilih validasi dalam)", x=0.01, y=1.04, ha="left", fontsize=10)
    fig.tight_layout()
    threshold_chart = save(fig, "07_sensitivitas_ambang.png")
    return roi_chart, tornado_chart, threshold_chart


# ---------------------------------------------------------------------------
# 5. Pola degradasi
# ---------------------------------------------------------------------------
TRAJECTORY_FEATURES = [("duty_60", "Duty 60 menit"), ("load_run_min", "Lama berbeban terus-menerus (menit)"), ("oil_mean_15", "Suhu oli 15 menit (°C)"), ("curr_mean_60", "Arus motor 60 menit (A)")]


def degradation_tables(online):
    valid = online[online["data_ok"] & ~online["in_grace"]]
    bins = [-0.001, 0.001, 2, 6, 12, 24, 48, 71.99]  # RUL 72 (kondisi sehat) tidak masuk jendela mana pun.
    labels = ["Failure", "0-2 j", "2-6 j", "6-12 j", "12-24 j", "24-48 j", "48-72 j"]
    rows = []
    healthy = valid[(valid["segment"] == 5) & (valid["RUL_Hours"] >= RUL_CAP)]
    for f in FAILURES.itertuples():
        seg = valid[valid["segment"] == f.id]
        cut = pd.cut(seg["RUL_Hours"], bins, labels=labels, include_lowest=True)
        g = seg.groupby(cut, observed=False)[[c for c, _ in TRAJECTORY_FEATURES]].mean()
        for label, values in g.iterrows():
            rows.append({"failure": f"F{f.id}", "jendela": label, **values.round(3).to_dict(), "n_menit": int((cut == label).sum())})
    table = pd.DataFrame(rows)
    reference = {c: round(float(healthy[c].quantile(0.95)), 3) for c, _ in TRAJECTORY_FEATURES}
    return table, reference


def precursor_table():
    rows = []
    for f in FAILURES.itertuples():
        before = EVENTS[(~EVENTS["official"]) & (EVENTS["end"] < f.start) & (EVENTS["start"] >= f.start - pd.Timedelta(days=14))]
        rows.append(
            {
                "failure": f"F{f.id} ({f.start:%d %b})",
                "kejadian_kecil_14_hari_sebelumnya": ", ".join(before["id"]) if len(before) else "-",
                "jarak_terdekat_hari": round((f.start - before["end"].max()).total_seconds() / 86400, 1) if len(before) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def precursor_rate(days=7):
    """Berapa kejadian kecil yang diikuti kegagalan resmi dalam 'days' hari (nilai prediktif positif aturan prekursor)."""
    minor = EVENTS[~EVENTS["official"]]
    followed = []
    for e in minor.itertuples():
        nxt = FAILURES[FAILURES["start"] > e.end]
        followed.append(bool(len(nxt)) and (nxt["start"].iloc[0] - e.end) <= pd.Timedelta(days=days))
    return sum(followed), len(minor)


def trajectory_chart(online, reference):
    fig, axes = plt.subplots(len(TRAJECTORY_FEATURES), 1, figsize=(10, 9), sharex=True)
    palette = [COLORS["s1"], COLORS["s2"], COLORS["s3"], "#6250d6"]
    for ax, (column, title) in zip(axes, TRAJECTORY_FEATURES):
        for color, f in zip(palette, FAILURES.itertuples()):
            window = online[(online.index >= f.start - pd.Timedelta(hours=72)) & (online.index <= f.start + pd.Timedelta(hours=2))]
            hours = (window.index - f.start).total_seconds() / 3600
            series = window[column].where(window["data_ok"]).rolling(30, min_periods=5).mean()
            ax.plot(hours, series, color=color, linewidth=1.3, label=f"F{f.id}")
        ax.axhline(reference[column], color=COLORS["muted"], linestyle="--", linewidth=1, label="P95 kondisi sehat (Agu)")
        ax.axvline(0, color=COLORS["critical"], linewidth=0.8)
        ax.set_title(title, loc="left")
    axes[0].legend(frameon=False, ncol=5, loc="upper left", fontsize=8)
    axes[-1].set_xlabel("Jam relatif terhadap awal kegagalan (0 = label failure mulai)")
    fig.tight_layout()
    return save(fig, "08_lintasan_degradasi.png")


def importance(bundle):
    rows = []
    for name, (model, _) in zip(bundle["anomaly_member_names"], bundle["anomaly_members"]):
        values = model.feature_importances_
        rows.append(pd.Series(values / values.sum(), index=bundle.get("anomaly_features", FEATURES), name=f"anomali_{name}"))
    rul = bundle["rul_model"].feature_importances_
    rows.append(pd.Series(rul / rul.sum(), index=bundle.get("rul_features", FEATURES), name="rul_xgb"))
    table = pd.concat(rows, axis=1)
    table["anomali"] = table[[c for c in table.columns if c.startswith("anomali_")]].mean(axis=1)
    return table[["anomali", "rul_xgb"]]


def importance_chart(table):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, column, title, color in ((axes[0], "anomali", "Model anomali final", COLORS["s1"]), (axes[1], "rul_xgb", "Model RUL final", COLORS["s2"])):
        top = table[column].dropna().sort_values(ascending=False).head(10).iloc[::-1]
        ax.barh(top.index, top.to_numpy(), color=color, height=0.6)
        ax.set_title(f"{title}: 10 fitur terpenting")
        ax.set_xlabel("Porsi kepentingan")
        ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return save(fig, "09_fitur_penting.png")


# ---------------------------------------------------------------------------
# Laporan
# ---------------------------------------------------------------------------
def main():
    ensure_dirs()
    train_table, online = load_tables()
    pred = pd.read_parquet(MODEL_DIR / "prediksi_walkforward.parquet")
    bundle = joblib.load(FINAL_DIR / "model_final.joblib")

    anomaly, rul, targets, choices, chart_models = model_summary()
    chart_rel = reliability_chart()
    chart_rul = rul_chart(pred[pred["rul_pred"].notna()], online)

    rows = online.loc[pred.index]
    step = online.index.to_series()[online["data_ok"]].diff()
    gaps = step[step > pd.Timedelta(minutes=30)].index
    fp_red = fp_table(pred["status_final"] == "Merah", rows, train_table, gaps, "Merah")
    fp_warn = fp_table(pred["status_final"].isin(["Kuning", "Merah"]), rows, train_table, gaps, "Kuning atau Merah")
    fn = fn_table(pred, online)
    chart_fp = fp_chart(fp_red, fp_warn)
    conf = confusion(pred)

    detection = detection_inputs(pred["status_final"])  # Sistem hybrid final (model terkalibrasi), walk-forward.
    roi_table = roi_tables(detection)
    tornado_table, base_roi = tornado(detection)
    breakeven = break_even(detection)
    curve = threshold_curve(pred)
    chosen = sorted(pred.loc[pred["model_aktif"], "ambang_anomali"].unique())
    chart_roi, chart_tornado, chart_thr = roi_charts(roi_table, tornado_table, base_roi, curve, chosen)

    degr, reference = degradation_tables(online)
    precursors = precursor_table()
    precursor_followed = precursor_rate()
    chart_traj = trajectory_chart(online, reference)
    imp = importance(bundle)
    chart_imp = importance_chart(imp)

    pd.concat([fp_red, fp_warn]).to_csv(MODEL_DIR / "analisis_fp.csv", index=False)
    fn.to_csv(MODEL_DIR / "analisis_fn.csv", index=False)
    roi_table.to_csv(MODEL_DIR / "analisis_roi.csv", index=False)
    tornado_table.to_csv(MODEL_DIR / "analisis_sensitivitas.csv", index=False)
    curve.to_csv(MODEL_DIR / "analisis_ambang.csv", index=False)
    degr.to_csv(MODEL_DIR / "analisis_degradasi.csv", index=False)
    imp.to_csv(MODEL_DIR / "analisis_fitur_penting.csv")

    true_rul = online.loc[pred.index, "RUL_Hours"]
    pre_failure = (true_rul > 0) & (true_rul < RUL_CAP)
    naive_rul_pra_mae = float((RUL_CAP - true_rul[pre_failure]).mean())
    write_report(locals())
    print(f"Laporan: {MODEL_DIR / 'LAPORAN_ANALISIS.md'}")


def write_report(v):
    anomaly, rul, targets, choices = v["anomaly"], v["rul"], v["targets"], v["choices"]
    fp_red, fp_warn, fn, conf = v["fp_red"], v["fp_warn"], v["fn"], v["conf"]
    roi_table, tornado_table, breakeven, curve = v["roi_table"], v["tornado_table"], v["breakeven"], v["curve"]
    degr, reference, precursors, imp, detection = v["degr"], v["reference"], v["precursors"], v["imp"], v["detection"]
    final_rul = pd.read_csv(MODEL_DIR / "final_rul.csv").iloc[0]
    final_rul_seg = pd.read_csv(MODEL_DIR / "final_rul_per_segmen.csv")
    base_rul = pd.read_csv(MODEL_DIR / "baseline_rul.csv").query("skema == 'walk'").set_index("model")

    a = anomaly.set_index("metode")
    red = a.loc["Hybrid final Merah"]
    old_red = a.loc["Hybrid lama Merah (HGB 0,5)"]
    t = targets.set_index("metrik")
    passed = int((targets["status"] == "LULUS").sum())
    near_label = int((fp_red["kategori"] == "Dekat batas kejadian berlabel (<= 6 jam)").sum()) if len(fp_red) else 0
    fp_after_gap = int((fp_red["kategori"] == "Sesudah gap data").sum()) if len(fp_red) else 0
    dasar = roi_table.set_index("skenario").loc["Dasar"]
    be = breakeven.set_index("parameter")["titik_impas"]
    positive = roi_table.loc[roi_table["roi_vs_reaktif_persen"] > 0, "skenario"].tolist()
    negative = roi_table.loc[roi_table["roi_vs_reaktif_persen"] <= 0, "skenario"].tolist()
    followed, n_minor = v["precursor_followed"]
    f4_delay = fn.set_index("kejadian").loc["E15_F4", "delay_merah_menit"]
    f4 = degr[degr["failure"] == "F4"].set_index("jendela")
    anomaly_top = imp["anomali"].sort_values(ascending=False).head(4).index.tolist()
    rul_top = imp["rul_xgb"].sort_values(ascending=False).head(3).index.tolist()
    missed_red = fn.loc[~fn["merah"], "kejadian"].tolist()
    weeks = TEST_WEEKS

    # Tabel dengan judul kolom yang mudah dibaca.
    anomaly_show = anomaly.assign(metode=anomaly["metode"].map(METHOD_NAMES)).rename(
        columns={"metode": "Metode", "kejadian": "Kejadian terdeteksi", "resmi": "Kegagalan resmi", "alarm_palsu": "Alarm palsu",
                 "delay_median_menit": "Delay median (menit)", "f1_baris": "F1 per menit", "pr_auc": "PR-AUC", "brier": "Brier"}
    )
    anomaly_show["Delay median (menit)"] = anomaly_show["Delay median (menit)"].map(lambda x: num(x, 1))
    model_names = {"xgb_dangkal": "XGBoost dangkal", "xgb_sedang": "XGBoost sedang", "xgb_dalam": "XGBoost dalam", "rf": "Random Forest", "ensemble": "Ensemble"}
    month_names = {"Apr": "April", "May": "Mei", "Jun": "Juni", "Jul": "Juli", "Aug": "Agustus"}
    rul_show = rul.assign(model=["Baseline Random Forest", "Baseline XGBoost", "Model final"]).rename(
        columns={"model": "Model", "mae_semua": "MAE semua (jam)", "mae_degradasi": "MAE degradasi (jam)",
                 "mae_pra_failure": "MAE pra-failure (jam)", "mae_kritis_24j": "MAE <= 24 jam",
                 "nasa_skor_degradasi": "Skor NASA", "f1_makro_stage": "F1 tahap", "recall_critical": "Recall Critical", "alarm_rul_palsu_total": "Alarm RUL palsu"}
    )
    rul_seg_show = final_rul_seg[["segmen_uji", "mae_semua", "mae_pra_failure", "mae_degradasi_tanpa_override", "f1_makro_stage", "recall_critical", "cakupan_interval"]].rename(
        columns={"segmen_uji": "Segmen uji", "mae_semua": "MAE semua", "mae_pra_failure": "MAE pra-failure",
                 "mae_degradasi_tanpa_override": "MAE degradasi tanpa override",
                 "f1_makro_stage": "F1 tahap", "recall_critical": "Recall Critical", "cakupan_interval": "Cakupan interval"}
    )
    choice_a = choices[choices["bagian"] == "anomali"][["bulan", "kejadian_diketahui", "model", "ambang"]].copy()
    choice_a["kejadian_diketahui"] = choice_a["kejadian_diketahui"].astype(int)
    choice_a["model"] = choice_a["model"].map(lambda m: model_names.get(m, m))
    choice_a["bulan"] = choice_a["bulan"].map(month_names)
    choice_a = choice_a.rename(columns={"bulan": "Bulan uji", "kejadian_diketahui": "Kejadian di data latih", "model": "Model terpilih", "ambang": "Ambang"}).astype(object).fillna("-")
    choice_r = choices[choices["bagian"] == "RUL"][["segmen_uji", "model", "ambang", "validasi_dalam"]].copy()
    choice_r["segmen_uji"] = choice_r["segmen_uji"].astype(int)
    choice_r["model"] = choice_r["model"].map(lambda m: model_names.get(m, m))
    choice_r = choice_r.rename(columns={"segmen_uji": "Segmen uji", "model": "Model terpilih", "ambang": "Ambang alarm (jam)", "validasi_dalam": "Validasi"})
    targets_show = targets.assign(hasil=[num(x, 4) if abs(x) < 1 else num(x, 2) for x in targets["hasil"]]).rename(
        columns={"area": "Area", "metrik": "Metrik", "target": "Target", "hasil": "Hasil", "status": "Status"}
    )
    targets_show["Status"] = targets_show["Status"].str.capitalize()
    targets_show["Target"] = targets_show["Target"].str.replace(">=", "≥").str.replace("<=", "≤").str.replace(r"(\d)\.(\d)", r"\1,\2", regex=True).str.replace("-", " - ")
    conf_show = conf.rename(columns={"": "Kondisi sebenarnya"})
    fp_show = fp_red[["mulai", "menit", "kejadian_terdekat", "posisi", "jarak_ke_kejadian_jam", "duty_60", "load_run_min", "oil_mean_15", "kategori"]].rename(
        columns={"mulai": "Mulai", "menit": "Durasi (menit)", "kejadian_terdekat": "Kejadian terdekat", "posisi": "Posisi", "jarak_ke_kejadian_jam": "Jarak (jam)",
                 "duty_60": "Duty 60", "load_run_min": "Berbeban (menit)", "oil_mean_15": "Suhu oli (°C)", "kategori": "Kategori"}
    ) if len(fp_red) else None
    fn_show = fn[["kejadian", "resmi", "durasi_menit", "merah", "kuning_atau_merah", "delay_merah_menit", "penyebab_terlewat"]].rename(
        columns={"kejadian": "Kejadian", "resmi": "Kegagalan resmi", "durasi_menit": "Durasi (menit)", "merah": "Merah", "kuning_atau_merah": "Kuning/Merah",
                 "delay_merah_menit": "Delay Merah (menit)", "penyebab_terlewat": "Keterangan"}
    )
    params = pd.DataFrame(ROI_SCENARIOS).reset_index().rename(columns={"index": "Parameter"})
    param_keys = params["Parameter"].copy()
    params["Parameter"] = params["Parameter"].map(PARAM_LABELS)
    monetary = {
        "biaya_downtime_per_jam", "biaya_perbaikan_darurat", "biaya_penggantian_preventif",
        "biaya_perbaikan_terencana", "biaya_inspeksi", "biaya_sistem",
    }
    for col in ("Batas rendah", "Dasar", "Batas tinggi"):
        params[col] = [
            f"{num(x * 100, 0)}%" if key == "kegagalan_lolos_preventif"
            else ub(x) if key in monetary
            else num(x, 2 if key in {"kegagalan_per_unit_tahun", "downtime_jam_per_kegagalan"} else 0)
            for key, x in zip(param_keys, params[col])
        ]
    roi_show = pd.DataFrame(
        {
            "Skenario": roi_table["skenario"],
            "TP/tahun": roi_table["tp_per_tahun"].map(lambda x: num(x, 1)),
            "FN/tahun": roi_table["fn_per_tahun"].map(lambda x: num(x, 1)),
            "FP/tahun": roi_table["fp_per_tahun"].map(lambda x: num(x, 1)),
            "Biaya reaktif/tahun (UB)": roi_table["biaya_reaktif_per_tahun"].map(ub),
            "Biaya preventif/tahun (UB)": roi_table["biaya_preventif_per_tahun"].map(ub),
            "Biaya prediktif/tahun (UB)": roi_table["biaya_prediktif_per_tahun"].map(ub),
            "Penghematan vs reaktif/tahun (UB)": roi_table["penghematan_vs_reaktif_per_tahun"].map(ub),
            "ROI vs reaktif": roi_table["roi_vs_reaktif_persen"].map(lambda x: f"{num(x, 1)}%"),
            "Penghematan vs preventif/tahun (UB)": roi_table["penghematan_vs_preventif_per_tahun"].map(ub),
            "ROI vs preventif": roi_table["roi_vs_preventif_persen"].map(lambda x: f"{num(x, 1)}%"),
        }
    )
    tornado_show = tornado_table.rename(columns={"parameter": "Parameter", "roi_turun_30": "ROI jika -30% (%)", "roi_naik_30": "ROI jika +30% (%)", "rentang": "Rentang (poin %)"})
    breakeven_show = breakeven.assign(
        nilai_dasar=[num(x, 2) for x in breakeven["nilai_dasar"]], titik_impas=[num(x, 2) for x in breakeven["titik_impas"]]
    ).rename(columns={"parameter": "Parameter", "nilai_dasar": "Nilai dasar", "titik_impas": "Titik impas", "arah": "Syarat ROI positif"})
    curve_show = curve[["ambang", "kejadian_mei_agu", "alarm_palsu", "delay_median_menit", "penghematan_vs_reaktif_per_tahun_dasar"]].copy()
    curve_show["penghematan_vs_reaktif_per_tahun_dasar"] = curve_show["penghematan_vs_reaktif_per_tahun_dasar"].map(ub)
    curve_show = curve_show.rename(columns={"ambang": "Ambang", "kejadian_mei_agu": "Kejadian Mei-Agu (dari 12)", "alarm_palsu": "Alarm palsu",
                                            "delay_median_menit": "Delay median (menit)", "penghematan_vs_reaktif_per_tahun_dasar": "Penghematan vs reaktif/tahun (dasar, UB)"})
    degr_show = degr[degr["n_menit"] > 0].rename(columns={"failure": "Kegagalan", "jendela": "Waktu sebelum kegagalan", "duty_60": "Duty 60", "load_run_min": "Berbeban (menit)",
                                                          "oil_mean_15": "Suhu oli (°C)", "curr_mean_60": "Arus motor (A)", "n_menit": "Jumlah menit"})
    precursor_show = precursors.rename(columns={"failure": "Kegagalan", "kejadian_kecil_14_hari_sebelumnya": "Kejadian kecil 14 hari sebelumnya", "jarak_terdekat_hari": "Jarak terdekat (hari)"})
    top_imp = imp.sort_values("anomali", ascending=False).head(8).round(3).reset_index().rename(columns={"index": "Fitur", "anomali": "Model anomali", "rul_xgb": "Model RUL"})
    top_rul = imp.sort_values("rul_xgb", ascending=False).head(8).round(3).reset_index().rename(columns={"index": "Fitur", "anomali": "Model anomali", "rul_xgb": "Model RUL"})

    text = f"""# Laporan Proyek: Pemeliharaan Prediktif Kompresor Udara Kereta Metro

**Proyek ManPro Kelompok 20**
Dataset: MetroPT-3, unit produksi udara (APU) kereta Metro do Porto, Februari-Agustus 2020

---

## Ringkasan

Proyek ini membangun sistem pemantauan kompresor udara yang mendeteksi anomali dan memperkirakan sisa umur
pakai (Remaining Useful Life, RUL). Hasil utama, diukur dengan validasi walk-forward April-Agustus 2020:

- Sistem final mendeteksi **{red['kejadian']} kejadian** dan **{red['resmi']} kegagalan resmi** dengan alarm Merah, dengan delay median
  {num(red['delay_median_menit'], 0)} menit. Alarm palsu Merah tercatat {red['alarm_palsu']} kali dalam {num(weeks, 0)} minggu ({num(red['alarm_palsu'] / weeks, 2)} per minggu).
- Skor anomali sudah terkalibrasi (ECE {num(t.loc['Model terkalibrasi: ECE Mei-Agu', 'hasil'], 4)}), sehingga bisa dibaca sebagai perkiraan peluang.
- MAE semua baris RUL adalah {num(final_rul['mae_semua'], 1)} jam, tetapi MAE pra-failure
  {num(final_rul['mae_pra_failure'], 1)} jam dibanding baseline sederhana RUL tetap 72 jam
  ({num(v['naive_rul_pra_mae'], 1)} jam). Tidak ada kegagalan yang diperingatkan sebelumnya pada validasi walk-forward;
  MAE semua baris didominasi menit sehat dan tidak membuktikan kemampuan prediksi dini.
- {passed} dari {len(targets)} target metrik tercapai.
- Pada nilai dasar, ROI prediktif adalah {num(dasar['roi_vs_reaktif_persen'], 1)}% terhadap reaktif dan
  {num(dasar['roi_vs_preventif_persen'], 1)}% terhadap preventif, berdasarkan biaya tahunan dalam UB.
  ROI terhadap reaktif positif pada: {', '.join(positive) if positive else 'tidak ada skenario'}.
- Insight terpenting: setiap kegagalan resmi didahului kejadian kecil dalam 2-7 hari, sehingga kejadian kecil layak
  dijadikan pemicu inspeksi.

---

## 1. Pendahuluan

### 1.1 Latar belakang

Kompresor udara (Air Production Unit, APU) menyuplai udara bertekanan untuk rem, suspensi, dan pintu kereta.
Kegagalan APU di tengah operasi membuat kereta harus ditarik dari layanan dan mengganggu jadwal. Selama ini
pemeliharaan dilakukan secara terjadwal atau sesudah kerusakan terjadi. Data sensor yang sudah tersedia memberi
peluang untuk mendeteksi masalah lebih awal.

### 1.2 Tujuan

1. Membangun model baseline untuk deteksi anomali dan RUL, lalu mengukur kinerjanya.
2. Mengembangkan model final yang terkalibrasi, dengan ambang yang dioptimasi, dan siap dipakai pada data baru.
3. Menganalisis kesalahan model, nilai bisnisnya, sensitivitas terhadap asumsi, serta pola degradasi mesin.

### 1.3 Ruang lingkup

Satu unit APU, data Februari-Agustus 2020. Analisis biaya memakai asumsi karena dataset tidak memuat data biaya.

---

## 2. Data

| Aspek | Keterangan |
|---|---|
| Sumber | MetroPT-3 (UCI Machine Learning Repository), 1.516.948 baris, interval 10 detik |
| Sensor | 7 analog (tekanan, suhu oli, arus motor) dan 8 digital |
| Agregasi | Rata-rata per menit, 51 fitur yang hanya melihat ke belakang (jendela 15, 60, dan 360 menit) |
| Label anomali | 16 kejadian dari Tabel II Davari dkk. (2021), termasuk 4 kegagalan resmi (F1-F4) |
| Label RUL | Jam menuju awal kegagalan resmi berikutnya, dibatasi 72 jam |
| Data dikecualikan | Sensor beku, data kosong, dan masa antara kegagalan dan perbaikan |

Persiapan data mengikuti pipeline yang sudah ada di proyek ini (`preprocess_dataprep.py`).

---

## 3. Metodologi

### 3.1 Skema validasi

Data deret waktu tidak boleh dibagi acak, karena menit yang berdekatan hampir identik. Proyek ini memakai
**validasi walk-forward**: setiap bulan (anomali) atau segmen menuju kegagalan (RUL) diuji oleh model yang hanya
dilatih dengan data sebelumnya. Semua pilihan model, kalibrasi, dan ambang ditentukan dari data latih, tidak pernah
dari data uji.

Kejadian dinilai per kejadian: kejadian dianggap terdeteksi jika ada alarm antara 2 jam sebelum mulai sampai akhir
kejadian. Alarm palsu adalah episode alarm yang tidak menyentuh kejadian mana pun.

### 3.2 Model baseline

- **Anomali**: Random Forest dan XGBoost, 51 fitur, ambang 0,5, tanpa penyetelan.
- **RUL**: Random Forest dan XGBoost regresi, alarm jika prediksi RUL di bawah 24 jam.

### 3.3 Model final

**Deteksi anomali**
1. Kandidat: XGBoost dangkal, XGBoost sedang, Random Forest, dan rata-rata ketiganya (ensemble).
2. Validasi dalam dengan GroupKFold per kelompok kejadian, untuk memilih kandidat.
3. Kalibrasi isotonic, sehingga skor 0,8 berarti sekitar 80% menit dengan skor itu memang kejadian.
4. Ambang dipilih dengan biaya terkecil, dengan asumsi satu kejadian terlewat setara 10 alarm palsu.
5. Skor terkalibrasi dipakai dalam aturan status hybrid (Hijau/Kuning/Merah/Abu-abu). Pada April, saat belum ada
   label, IsolationForest menangani peringatan (aturan cold start).

**RUL**
1. XGBoost regresi, hiperparameter dipilih dengan validasi expanding-window yang hanya memakai data masa lalu.
2. Kalibrasi isotonic untuk menghapus bias prediksi.
3. Saat model anomali mendeteksi pola kegagalan, RUL ditetapkan 0 (tahap Failure).
4. Interval prediksi 80% dengan metode conformal.

### 3.4 Target metrik

Target ditetapkan setelah melihat hasil baseline, sebelum model final dijalankan:

{md_table(targets_show[["Area", "Metrik", "Target"]])}

---

## 4. Hasil Pemodelan

### 4.1 Deteksi anomali

![Perbandingan baseline dan model final]({v['chart_models']})

{md_table(anomaly_show, 3)}

Baseline dan model final tunggal hanya mendeteksi 12 kejadian, karena April belum memiliki label sehingga tidak ada
model supervised. Sistem hybrid menutup celah ini dengan IsolationForest, sehingga F1 tetap terdeteksi.

Dibanding sistem hybrid versi awal (HGB, ambang tetap 0,5), sistem final mendeteksi kejadian yang sama
({old_red['kejadian']} berbanding {red['kejadian']}), dengan alarm palsu {red['alarm_palsu']} berbanding {old_red['alarm_palsu']}.
Model supervised final memakai 9 fitur proses yang sama dengan HGB (duty, siklus, suhu oli, arus, tekanan). Versi dengan
51 fitur menghasilkan 10 alarm palsu karena ikut mempelajari fluktuasi sensor sesaat. Catatan kejujuran: keputusan
memakai 9 fitur, baik di HGB maupun di model final, diambil setelah membandingkan hasil walk-forward yang sama, sehingga
angka alarm palsu ini sedikit optimistis dan perlu dikonfirmasi pada data sesudah Agustus 2020. Pemilihan model,
kalibrasi, dan ambang tiap bulan tetap dibuat hanya dari data latih.

Model yang terpilih tiap bulan:

{md_table(choice_a, 2)}

![Reliabilitas skor]({v['chart_rel']})

Grafik reliabilitas menunjukkan skor terkalibrasi mengikuti garis diagonal: skor model sesuai dengan frekuensi kejadian
yang sebenarnya.

### 4.2 RUL

{md_table(rul_show, 2)}

Per segmen uji (model final; MAE pra-failure hanya menghitung label 0 < RUL < 72 jam):

{md_table(rul_seg_show, 2)}

Model yang terpilih tiap segmen:

{md_table(choice_r)}

![Prediksi RUL]({v['chart_rul']})

Grafik di atas memperlihatkan keterbatasan utama: sebelum F2 dan F3, prediksi tetap di sekitar 70 jam sampai kegagalan
terjadi. Skor RUL perlu dibaca pada jendela pra-failure, bukan hanya dari MAE semua baris. Karena validasi walk-forward
belum menghasilkan lead-time, tampilkan RUL sebagai perkiraan eksperimental beserta tahap dan interval, bukan sebagai
janji hitung mundur atau rekomendasi penggantian otomatis.

### 4.3 Capaian target

{md_table(targets_show)}

Target yang belum tercapai:
- **Brier skor anomali** {num(t.loc['Model terkalibrasi: Brier skor Mei-Agu', 'hasil'], 4)}, sedikit di atas target 0,0019.
- **MAE pra-failure RUL** {num(final_rul['mae_pra_failure'], 1)} jam, di atas target 12 jam. Cakupan interval keseluruhan
  {num(final_rul['cakupan_interval'] * 100, 1)}% masih dalam target 70-90%, tetapi cakupan pra-failure hanya
  {num(final_rul['cakupan_pra_failure'] * 100, 1)}%, sehingga intervalnya belum dapat diandalkan saat degradasi.
- **Peringatan RUL sebelum kegagalan** tidak tercapai. Bagian 8 menunjukkan bahwa sinyal 6-72 jam sebelumnya memang
  tidak ada pada F1-F3. Baseline XGBoost sempat memberi peringatan, tetapi dengan {int(base_rul.loc['XGBoost', 'alarm_rul_palsu_total'])} alarm palsu.

---

## 5. Analisis Kesalahan (False Positive dan False Negative)

### 5.1 Matriks kebingungan per menit

Model terkalibrasi, Mei-Agustus 2020. Menit dalam margin 2 jam di sekitar kejadian tidak dihitung.

{md_table(conf_show)}

### 5.2 Alarm palsu (False Positive)

Daftar alarm palsu Merah, yaitu yang dikirim sebagai notifikasi ke teknisi:

{md_table(fp_show, 2) if fp_show is not None else 'Tidak ada alarm palsu Merah.'}

![Kategori alarm palsu]({v['chart_fp']})

Temuan:
1. Semua alarm palsu Merah berdurasi pendek (1-71 menit).
2. {near_label} dari {len(fp_red)} terjadi kurang dari 6 jam dari kejadian berlabel. Pola sensornya mirip kejadian di dekatnya,
   sehingga kemungkinan besar mesin belum pulih sepenuhnya atau label kejadian terlalu sempit.
3. {fp_after_gap} alarm muncul sesaat setelah data sensor kembali dari gap, saat fitur rata-rata bergerak belum stabil.
4. Alarm Kuning palsu lebih banyak ({len(fp_warn)} episode, {num(len(fp_warn) / weeks, 1)} per minggu). Kuning hanya tampil di dashboard,
   tidak dikirim sebagai notifikasi.

### 5.3 Kejadian terlewat (False Negative)

{md_table(fn_show, 0)}

Temuan:
1. Kejadian yang tidak mencapai Merah: {', '.join(missed_red) if missed_red else 'tidak ada'}. Keduanya kejadian singkat di April, saat model
   supervised belum tersedia. Keduanya tetap muncul sebagai Kuning.
2. Semua kejadian Mei-Agustus dan keempat kegagalan resmi mencapai Merah.
3. F4 sudah berstatus Merah {num(abs(f4_delay), 0)} menit sebelum label kegagalan dimulai, sejalan dengan pola degradasi bertahap F4.
4. Delay median sekitar {num(red['delay_median_menit'], 0)} menit menunjukkan sistem ini bekerja sebagai **deteksi dini**, bukan peramalan
   berhari-hari sebelumnya.

---

## 6. Analisis Bisnis: Simulasi ROI

### 6.1 Asumsi

Perhitungan memakai **1 UB = biaya satu perbaikan terencana** sesuai definisi dokumen. Biaya dasar dan batas rendah/tinggi
berikut mengikuti tabel asumsi biaya yang disepakati:

{md_table(params)}

Dokumen tidak menetapkan frekuensi kegagalan dan durasi downtime. Untuk ilustrasi, frekuensi dasar diambil dari 4
kegagalan resmi selama {num(OBSERVED_MONTHS, 0)} bulan pada satu unit ({num(FAILURES_PER_UNIT_YEAR, 2)} kegagalan/tahun).
Durasi downtime diproksikan dengan rata-rata lama interval label 4 kegagalan ({num(DOWNTIME_HOURS_PER_FAILURE, 2)} jam),
bukan catatan downtime operasional terverifikasi. Ganti kedua nilai ini dengan data operasional bila tersedia.

Metrik deteksi diambil dari validasi walk-forward sistem hybrid final, bukan LOFO: recall kegagalan resmi {detection['recall_resmi']:.0%}
dan {num(detection['alarm_palsu_per_minggu'], 2)} episode alarm Merah palsu per minggu per unit. Walk-forward dipakai
untuk menghindari pelatihan dengan data masa depan; ini merupakan perbedaan metode dari LOFO yang disebut dokumen.
Kejadian kecil yang tidak cocok dengan kegagalan resmi dihitung konservatif sebagai FP.

Perhitungan per tahun mengikuti rumus ruang lingkup:
- Reaktif = N kegagalan × (jam downtime × biaya downtime/jam + perbaikan darurat).
- Preventif = jumlah penggantian terjadwal × biaya penggantian per penggantian + biaya kegagalan yang lolos.
- Prediktif = TP × perbaikan terencana + FN × biaya kegagalan reaktif + FP × inspeksi + biaya operasi sistem.
- TP/FN dihitung dari frekuensi kegagalan tahunan × recall; FP dari episode alarm Merah tanpa kegagalan resmi yang cocok
  (alarm pada masa maintenance dikecualikan), dianualisasi per unit.
- Penghematan prediktif terhadap strategi = biaya strategi pembanding − biaya prediktif.
- ROI tahunan terhadap tiap pembanding = penghematan tahunan ÷ biaya sistem tahunan × 100%.
- Tidak ditampilkan NPV, balik modal, atau capex: rumus tersebut tidak termasuk dalam asumsi ROI pada dokumen.

### 6.2 Hasil

{md_table(roi_show)}

![Simulasi ROI]({v['chart_roi']})

---

## 7. Analisis Sensitivitas

### 7.1 Sensitivitas parameter

Setiap parameter pada nilai dasar digeser ±30%, parameter lain tetap. ROI sensitivitas mengacu pada pembanding reaktif:

![Tornado sensitivitas]({v['chart_tornado']})

{md_table(tornado_show, 1)}

### 7.2 Titik impas

Nilai parameter yang membuat ROI terhadap reaktif tepat nol, parameter lain tetap pada nilai dasar:

{md_table(breakeven_show)}

### 7.3 Sensitivitas ambang

![Sensitivitas ambang]({v['chart_thr']})

{md_table(curve_show, 2)}

Kurva ini dihitung pada data uji, sehingga hanya menggambarkan trade-off dan tidak dipakai untuk memilih ambang.

### 7.4 Interpretasi

1. ROI paling dipengaruhi oleh **{tornado_table.iloc[0]['parameter'].lower()}**, **{tornado_table.iloc[1]['parameter'].lower()}**, dan
   **{tornado_table.iloc[2]['parameter'].lower()}**. Ketiganya asumsi bisnis, sehingga validasi data biaya lebih mendesak
   daripada peningkatan model.
2. Pada nilai dasar, ROI terhadap reaktif tetap positif selama alarm Merah tanpa kegagalan resmi di bawah {num(be.loc['Alarm Merah tanpa kegagalan resmi per minggu'], 2)} per minggu per unit
   (saat ini {num(detection['alarm_palsu_per_minggu'], 2)}).
3. Ambang 0,75-0,90 memberi alarm palsu paling sedikit tanpa kehilangan kejadian. Ambang yang dipilih model berada
   di kisaran 0,30-0,85, sehingga ada ruang perbaikan jika data latih bertambah.
4. Karena recall kegagalan resmi sudah 100% pada sampel kecil ini, model belum membuktikan lead-time yang memberi
   penghematan. ROI tetap simulasi bersyarat, bukan bukti kelayakan investasi.

---

## 8. Pola Degradasi dan Insight

### 8.1 Perilaku sensor menjelang kegagalan

![Lintasan sensor]({v['chart_traj']})

Rata-rata sensor per jendela waktu sebelum kegagalan. Sebagai acuan, persentil 95 kondisi sehat (Agustus): duty 60
menit {num(reference['duty_60'], 2)}, lama berbeban {num(reference['load_run_min'], 0)} menit, suhu oli {num(reference['oil_mean_15'], 1)} °C.

{md_table(degr_show, 2)}

Temuan:
1. **F1, F2, dan F3 terjadi mendadak.** Pada jam terakhir yang memiliki data sebelum kegagalan, duty kompresor masih
   sekitar 0,1, di bawah batas sehat. Saat gagal, kompresor bekerja terus-menerus (duty mendekati 1) tetapi tidak pernah
   mencapai tekanan target. Ini pola khas kebocoran udara.
2. **F4 menunjukkan degradasi bertahap.** Duty naik dari {num(f4.loc['24-48 j', 'duty_60'], 2)} (24-48 jam sebelumnya) menjadi {num(f4.loc['12-24 j', 'duty_60'], 2)} (12-24 jam),
   {num(f4.loc['2-6 j', 'duty_60'], 2)} (2-6 jam), dan {num(f4.loc['0-2 j', 'duty_60'], 2)} (0-2 jam). Arus motor juga naik bersamaan. Pola seperti ini dapat
   dipantau dengan aturan sederhana seperti "duty 6 jam di atas 0,3".
3. **Suhu oli naik sebagai akibat**, setelah kompresor bekerja lama, sehingga lebih cocok untuk konfirmasi daripada
   peringatan dini.

### 8.2 Kejadian kecil sebagai prekursor

{md_table(precursor_show, 1)}

Semua kegagalan resmi didahului kejadian kecil dalam 14 hari sebelumnya, dengan jarak terdekat
{num(precursors['jarak_terdekat_hari'].min(), 0)}-{num(precursors['jarak_terdekat_hari'].max(), 0)} hari. Sebaliknya, {followed} dari {n_minor} kejadian kecil diikuti kegagalan resmi dalam 7 hari.
Kejadian kecil yang sudah pulih sebaiknya tidak diabaikan, tetapi dijadikan pemicu inspeksi dalam seminggu.

### 8.3 Fitur yang paling berpengaruh

![Fitur terpenting]({v['chart_imp']})

Model anomali:

{md_table(top_imp, 3)}

Model RUL:

{md_table(top_rul, 3)}

- Model anomali terutama memakai {', '.join(anomaly_top)}: tekanan, laju pengisian tekanan, dan lama kompresor
  berbeban. Saat terjadi kebocoran, tekanan turun dan kompresor butuh waktu lebih lama untuk mengisi.
- Model RUL terutama memakai {', '.join(rul_top)}. Suhu oli dipengaruhi suhu lingkungan dan musim, sehingga model RUL
  perlu dilatih ulang secara berkala.

---

## 9. Kesimpulan dan Rekomendasi

### 9.1 Kesimpulan

1. Sistem hybrid final mendeteksi {red['kejadian']} kejadian dan semua kegagalan resmi, dengan skor yang terkalibrasi.
2. RUL belum menunjukkan lead-time pada walk-forward dan belum layak dipakai sendiri untuk menjadwalkan penggantian.
3. ROI tiga strategi hanya simulasi berbasis asumsi, dan sensitivitasnya bergantung pada frekuensi kegagalan serta
   biaya komponen, downtime, inspeksi, dan sistem.
4. Kejadian kecil adalah tanda peringatan terkuat menjelang kegagalan besar.

### 9.2 Rekomendasi

1. Gunakan sistem hybrid final untuk notifikasi Merah, dan tampilkan RUL sebagai tahap beserta intervalnya.
2. Tinjau ulang batas label bersama teknisi, terutama di sekitar E14 dan E16, untuk mengurangi alarm palsu.
3. Kumpulkan data biaya nyata (biaya per kegagalan, durasi gangguan, biaya inspeksi) untuk memperbarui analisis ROI.
4. Lakukan inspeksi dalam 7 hari setelah setiap kejadian kecil.
5. Latih ulang model setiap bulan. Model RUL membutuhkan lebih banyak data kegagalan (idealnya 10 atau lebih).

---

## 10. Keterbatasan

1. Hanya satu unit APU dengan 4 kegagalan resmi dan 16 kejadian, sehingga hasil perlu divalidasi pada data lain.
2. Target metrik ditetapkan oleh tim setelah melihat baseline.
3. Seluruh analisis biaya berbasis asumsi.
4. Kinerja model final yang diekspor (dilatih dengan seluruh data) belum dapat diukur langsung, sehingga diwakili oleh
   hasil walk-forward.

---

## Daftar Pustaka

- Davari, N., Veloso, B., Ribeiro, R. P., Pereira, P. M., & Gama, J. (2021). Predictive maintenance based on anomaly
  detection using deep learning for air production unit in the railway industry. *IEEE DSAA 2021*.
- Veloso, B., Ribeiro, R. P., Gama, J., & Pereira, P. M. (2022). The MetroPT dataset for predictive maintenance.
  *Scientific Data*, 9, 764.
- Saxena, A., Goebel, K., Simon, D., & Eklund, N. (2008). Damage propagation modeling for aircraft engine run-to-failure
  simulation. *PHM 2008*.

## Lampiran: Berkas Proyek

| Berkas | Isi |
|---|---|
| `train_baseline.py` | Pelatihan dan evaluasi model baseline |
| `train_final_calibrated.py` | Pelatihan model final, kalibrasi, optimasi ambang, ekspor model |
| `analysis_report.py` | Analisis dan pembuatan laporan ini |
| `predict.py` | Pemakaian model final pada data baru |
| `output/model/final/` | Model final dan metadata |
| `output/model/prediksi_walkforward.parquet` | Prediksi per menit April-Agustus 2020 |
"""
    (MODEL_DIR / "LAPORAN_ANALISIS.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
