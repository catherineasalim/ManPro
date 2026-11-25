"""Dashboard ROI assumptions copied from the latest project analysis report."""

DETECTION_DEFAULTS = {
    "official_recall": 1.0,
    "false_red_alarms_per_week": 0.7777777777777778,
}

RUPIAH_PER_UB = 50_000_000
FAILURES_PER_YEAR = 4 / 7 * 12
DOWNTIME_HOURS_PER_FAILURE = 21.870833333333334

SCENARIOS = {
    "Batas rendah": {
        "kegagalan_per_unit_tahun": FAILURES_PER_YEAR,
        "downtime_jam_per_kegagalan": DOWNTIME_HOURS_PER_FAILURE,
        "biaya_downtime_per_jam": 0.2,
        "biaya_perbaikan_darurat": 2.0,
        "biaya_perbaikan_terencana": 0.8,
        "biaya_inspeksi": 0.05,
        "interval_penggantian_bulan": 12.0,
        "biaya_penggantian_preventif": 1.0,
        "kegagalan_lolos_preventif": 0.1,
        "biaya_sistem": 0.5,
    },
    "Dasar": {
        "kegagalan_per_unit_tahun": FAILURES_PER_YEAR,
        "downtime_jam_per_kegagalan": DOWNTIME_HOURS_PER_FAILURE,
        "biaya_downtime_per_jam": 0.5,
        "biaya_perbaikan_darurat": 3.0,
        "biaya_perbaikan_terencana": 1.0,
        "biaya_inspeksi": 0.1,
        "interval_penggantian_bulan": 6.0,
        "biaya_penggantian_preventif": 1.2,
        "kegagalan_lolos_preventif": 0.3,
        "biaya_sistem": 1.0,
    },
    "Batas tinggi": {
        "kegagalan_per_unit_tahun": FAILURES_PER_YEAR,
        "downtime_jam_per_kegagalan": DOWNTIME_HOURS_PER_FAILURE,
        "biaya_downtime_per_jam": 1.5,
        "biaya_perbaikan_darurat": 5.0,
        "biaya_perbaikan_terencana": 1.5,
        "biaya_inspeksi": 0.2,
        "interval_penggantian_bulan": 3.0,
        "biaya_penggantian_preventif": 2.0,
        "kegagalan_lolos_preventif": 0.6,
        "biaya_sistem": 3.0,
    },
}
