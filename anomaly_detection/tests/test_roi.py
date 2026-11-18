"""Uji rumus biaya reaktif, preventif, dan prediktif."""
import unittest

import pandas as pd

from anomaly_detection.laporan.analysis_report import (
    DOWNTIME_HOURS_PER_FAILURE,
    FAILURES_PER_UNIT_YEAR,
    ROI_SCENARIOS,
    official_alarm_metrics,
    roi,
    ub,
)
from anomaly_detection.preprocessing.preprocess_iforest import EVENTS


class RoiTest(unittest.TestCase):
    def test_scenario_costs_follow_documented_ub_assumptions(self):
        base = ROI_SCENARIOS["Dasar"]
        self.assertEqual(base["biaya_perbaikan_terencana"], 1)
        self.assertEqual(base["biaya_perbaikan_darurat"], 3)
        self.assertEqual(base["biaya_downtime_per_jam"], 0.5)
        self.assertEqual(base["biaya_inspeksi"], 0.1)
        self.assertEqual(base["interval_penggantian_bulan"], 6)
        self.assertEqual(base["biaya_penggantian_preventif"], 1.2)
        self.assertEqual(base["kegagalan_lolos_preventif"], 0.3)
        self.assertEqual(base["biaya_sistem"], 1)
        self.assertAlmostEqual(FAILURES_PER_UNIT_YEAR, 4 / 7 * 12)
        self.assertAlmostEqual(
            DOWNTIME_HOURS_PER_FAILURE,
            (23 + 59 / 60 + 6.5 + 52.5 + 4.5) / 4,
        )
        self.assertEqual(ub(12.5), "12,50 UB")
        self.assertEqual(ub(-1.25), "-1,25 UB")

    def test_only_official_failures_count_as_true_positives(self):
        index = pd.date_range("2020-04-01", "2020-08-01", freq="1min")
        alarm = pd.Series(False, index=index)
        official = EVENTS[EVENTS["official"]].iloc[0]
        minor = EVENTS[~EVENTS["official"]].iloc[0]
        alarm.loc[official.start + pd.Timedelta(minutes=5)] = True
        alarm.loc[minor.start + pd.Timedelta(minutes=5)] = True
        alarm.loc[pd.Timestamp("2020-07-30 12:00")] = True

        result = official_alarm_metrics(alarm, weeks=10)

        self.assertEqual(result["recall_resmi"], 0.25)
        self.assertEqual(result["alarm_palsu_per_minggu"], 0.2)

    def test_strategy_costs_follow_project_scope_formulas(self):
        params = {
            "kegagalan_per_unit_tahun": 1,
            "downtime_jam_per_kegagalan": 3,
            "biaya_downtime_per_jam": 10,
            "biaya_perbaikan_darurat": 70,
            "interval_penggantian_bulan": 6,
            "biaya_penggantian_preventif": 30,
            "kegagalan_lolos_preventif": 0.5,
            "biaya_perbaikan_terencana": 40,
            "biaya_inspeksi": 2,
            "biaya_sistem": 30,
        }
        detection = {"recall_resmi": 0.75, "alarm_palsu_per_minggu": 2}

        result = roi(params, detection)

        self.assertEqual(result["biaya_reaktif_per_tahun"], 100)
        self.assertEqual(result["biaya_preventif_per_tahun"], 110)
        self.assertEqual(result["tp_per_tahun"], 0.75)
        self.assertEqual(result["fn_per_tahun"], 0.25)
        self.assertEqual(result["fp_per_tahun"], 104)
        self.assertEqual(result["biaya_prediktif_per_tahun"], 293)
        self.assertEqual(result["penghematan_vs_reaktif_per_tahun"], -193)
        self.assertEqual(result["penghematan_vs_preventif_per_tahun"], -183)
        self.assertAlmostEqual(result["roi_vs_reaktif_persen"], -193 / 30 * 100)
        self.assertAlmostEqual(result["roi_vs_preventif_persen"], -183 / 30 * 100)


if __name__ == "__main__":
    unittest.main()
