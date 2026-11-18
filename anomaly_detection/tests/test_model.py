"""
Uji fungsi bersama tahap lanjutan (model_utils.py dan train_final_calibrated.py) dengan data buatan.

Jalankan:  python -m anomaly_detection.tests.test_model
"""
import unittest

import numpy as np
import pandas as pd

from anomaly_detection.common.model_utils import event_level, nasa_score, rul_alert_eval, rul_metrics, rul_stage
from anomaly_detection.preprocessing.preprocess_iforest import EVENTS
from anomaly_detection.rul_final.train_final_calibrated import apply_conformal, event_groups, fit_conformal, inner_splits


def minutes(start, end):
    return pd.date_range(start, end, freq="1min", inclusive="left")


class EventLevelTest(unittest.TestCase):
    def setUp(self):
        self.index = minutes("2020-07-01", "2020-08-01")
        self.events = EVENTS[EVENTS["start"].between("2020-07-01", "2020-08-01")]

    def test_alarm_inside_event_is_hit(self):
        alarm = pd.Series(False, index=self.index)
        e = self.events.iloc[0]
        alarm[(alarm.index >= e.start) & (alarm.index <= e.start + pd.Timedelta(minutes=20))] = True
        result = event_level(alarm, self.events, self.index[0], self.index[-1])
        self.assertEqual(result["hits"], 1)
        self.assertEqual(len(result["false_alarms"]), 0)

    def test_alarm_far_from_events_is_false(self):
        alarm = pd.Series(False, index=self.index)
        alarm["2020-07-25 10:00":"2020-07-25 10:30"] = True
        result = event_level(alarm, self.events, self.index[0], self.index[-1])
        self.assertEqual(result["hits"], 0)
        self.assertEqual(len(result["false_alarms"]), 1)


class RulTest(unittest.TestCase):
    def test_nasa_penalises_late_more(self):
        true = np.array([10.0])
        self.assertGreater(nasa_score(true, true + 10), nasa_score(true, true - 10))

    def test_stage_edges(self):
        self.assertEqual(list(rul_stage([0, 6, 6.1, 24, 30])), ["Critical", "Critical", "Warning", "Warning", "Normal"])

    def test_perfect_prediction(self):
        true = np.array([72, 50, 10, 0], float)
        m = rul_metrics(true, true)
        self.assertEqual(m["mae_semua"], 0)
        self.assertEqual(m["akurasi_stage"], 1)

    def test_pre_failure_mae_excludes_censored_and_failure_rows(self):
        metrics = rul_metrics([72, 50, 10, 0], [0, 60, 8, 50])
        self.assertEqual(metrics["mae_pra_failure"], 6)

    def test_alert_lead_time(self):
        index = minutes("2020-07-12", "2020-07-15 14:30")  # Segmen menuju F4 (15 Jul 14:30).
        rows = pd.DataFrame(index=index)
        pred = pd.Series(72.0, index=index)
        pred["2020-07-15 02:30":] = 5.0  # Alarm 12 jam sebelum F4.
        r = rul_alert_eval(pred, rows, alert_hours=6)
        self.assertTrue(r["terdeteksi_sebelum_failure"])
        self.assertAlmostEqual(r["lead_time_jam"], 12, delta=0.5)
        self.assertEqual(r["alarm_palsu"], 0)

    def test_inner_rul_splits_only_use_past_segments(self):
        index = pd.date_range("2020-01-01", periods=9, freq="1min")
        table = pd.DataFrame(
            {
                "data_ok": True,
                "in_grace": False,
                "segment": np.repeat([1, 2, 3], 3),
                "RUL_Hours": 60.0,
            },
            index=index,
        )
        splits = list(inner_splits(table, [1, 2, 3]))
        self.assertEqual(len(splits), 2)
        for train, valid in splits:
            self.assertLess(train.index.max(), valid.index.min())
        self.assertEqual(set(splits[0][0]["segment"]), {1})
        self.assertEqual(set(splits[0][1]["segment"]), {2})
        self.assertEqual(set(splits[1][0]["segment"]), {1, 2})
        self.assertEqual(set(splits[1][1]["segment"]), {3})

    def test_single_segment_rul_splits_are_expanding_in_time(self):
        index = pd.date_range("2020-01-01", periods=8, freq="1min")
        table = pd.DataFrame(
            {"data_ok": True, "in_grace": False, "segment": 1, "RUL_Hours": 60.0},
            index=index,
        )
        splits = list(inner_splits(table, [1], n_blocks=4))
        self.assertEqual(len(splits), 3)
        for train, valid in splits:
            self.assertLess(train.index.max(), valid.index.min())


class CalibrationTest(unittest.TestCase):
    def test_conformal_coverage_on_its_own_data(self):
        rng = np.random.default_rng(0)
        pred = rng.uniform(0, 72, 5000)
        true = np.clip(pred + rng.normal(0, 5, 5000), 0, 72)
        lo, hi = apply_conformal(fit_conformal(true, pred), pred)
        coverage = np.mean((true >= lo) & (true <= hi))
        self.assertGreater(coverage, 0.78)
        self.assertTrue(np.all(lo <= pred) and np.all(hi >= pred))

    def test_close_events_share_a_group(self):
        events = EVENTS[EVENTS["id"].isin(["E03", "E04", "E14"])]
        index = pd.DatetimeIndex([pd.Timestamp("2020-04-29 03:30"), pd.Timestamp("2020-04-29 22:10"), pd.Timestamp("2020-07-08 18:00")])
        groups, n = event_groups(index, events)
        self.assertEqual(n, 2)
        self.assertEqual(groups[0], groups[1])
        self.assertNotEqual(groups[0], groups[2])


if __name__ == "__main__":
    unittest.main()
