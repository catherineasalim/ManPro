# Anomaly Detection on MetroPT-3

Anomaly detection for the air compressor (APU) of a Metro do Porto train, using the
[MetroPT-3 dataset](https://archive.ics.uci.edu/dataset/791/metropt+3+dataset).
The main model is a **hybrid system**:

- **IsolationForest** (unsupervised, 51 features) raises the early warning (Kuning / yellow).
- **HistGradientBoosting** (supervised, 9 features) raises the alarm (Merah / red) after it has seen past failures.
- In April, before any failure has been seen, an IsolationForest alarm that lasts 60 minutes turns red instead (the cold-start rule).

All code is in [`anomaly_detection/`](anomaly_detection/).

## Documentation

| Dokumentasi | Deskripsi |
|---|---|
| [Modul Anomaly Detection](anomaly_detection/README.md) | Struktur folder dan alur kerja pemodelan |
| [Dashboard](dashboard/README.md) | Fitur dashboard, sumber data, dan cara menjalankan |
| [Alur Dashboard](dashboard/ALUR.md) | Penjelasan detail alur data, model, replay, dan keluaran |
| [Laporan Analisis](anomaly_detection/output/model/LAPORAN_ANALISIS.md) | Hasil evaluasi model, RUL, dan simulasi ROI |

---

## 1. Get the dataset (not included in this repo)

The raw CSV is about **218 MB**. GitHub rejects files over 100 MB, so the CSV is not in the repo
(`.gitignore` excludes every `*.csv`). Download it yourself:

1. Go to <https://archive.ics.uci.edu/dataset/791/metropt+3+dataset> and click **Download**.
2. Extract the zip.
3. Put **`MetroPT3(AirCompressor).csv`** in the **repo root**, next to this README. Do not rename it.

```
Project-ManPro-kel-20/
├── MetroPT3(AirCompressor).csv     <- put the dataset here
├── README.md
└── anomaly_detection/
    ├── preprocessing/
    ├── anomali/
    ├── rul_final/
    ├── ...
    └── output/
```

The code finds the file through this line in `anomaly_detection/preprocessing/preprocess_iforest.py`
(`BASE_DIR` is the `anomaly_detection/` folder):

```python
CSV_PATH = BASE_DIR.parent / "MetroPT3(AirCompressor).csv"
```

If you want to keep the CSV somewhere else, change this line. Don't commit the CSV.

> **Check:** the file should have **1,516,948 rows**. `preprocess_dataprep.py` prints
> `baris mentah 1,516,948 OK` when the file is complete. Don't open and save it in Excel:
> Excel cuts it off at about 1,048,576 rows (26 June 2020) and you lose failure F4.

### Do I need the CSV?

The preprocessed 1-minute tables are already in the repo, so you can train the hybrid **without** the CSV.

| What you want to do | Need the CSV? |
|---|---|
| Train and evaluate the hybrid (`train_hybrid.py`) | No. It reads `output/dataprep/*.parquet` (already in the repo) |
| Run the unit tests (`test_hybrid.py`) | No. They use made-up data |
| Make the charts (`visualize_hybrid.py`) | No, but run `train_hybrid.py` first (see step 3) |
| Rebuild the preprocessing (`preprocess_dataprep.py`) | **Yes** |
| Run the older pipeline (`preprocess_iforest.py`, `model_iforest.py`, `model_supervised.py`) | **Yes** |

---

## 2. Setup

Tested with Python 3.12.

```bash
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# macOS / Linux:         source .venv/bin/activate

pip install numpy pandas scikit-learn joblib matplotlib pyarrow xgboost
```

Versions used during development: numpy 1.26.4, pandas 2.2.3, scikit-learn 1.6.0, joblib 1.4.2,
matplotlib 3.10.0, pyarrow 20.0.0.

---

## 3. Run the hybrid

Run every command from the **repo root** (the folder with this README), with `python -m`.
The code is split into subfolders by stage; the map of which file does what is in
[`anomaly_detection/README.md`](anomaly_detection/README.md).

To run every stage in order (tests, hybrid, charts, RUL models, report):

```bash
python -m anomaly_detection.run_all
```

Or run the hybrid steps one by one:

```bash
python -m anomaly_detection.preprocessing.preprocess_dataprep   # optional: only to rebuild output/dataprep/ from the CSV
python -m anomaly_detection.anomali.train_hybrid                # train + walk-forward evaluation, writes output/hybrid/
python -m anomaly_detection.tests.test_hybrid                   # 13 tests of the status rules (should end with "OK")
python -m anomaly_detection.anomali.visualize_hybrid            # 8 PNG charts for the report -> output/hybrid/grafik/
```

**After a fresh clone, run `train_hybrid.py` before `visualize_hybrid.py`.** The charts read
`hasil_hybrid.csv`, `kejadian_hybrid.csv`, `alarm_hybrid.csv` and `tradeoff_hybrid.csv`.
These are not in the repo (they match `*.csv` in `.gitignore`), so `train_hybrid.py` has to create them first.

### Options for `train_hybrid.py`

```bash
python -m anomaly_detection.anomali.train_hybrid --seeds 42 7 --labels 16 4 --train-days 60   # these are the defaults
```

| Option | Meaning |
|---|---|
| `--seeds` | Random seeds. Results are reported per seed |
| `--labels` | `16` = the 16 events from Davari et al. (2021) Table II (main labels), `4` = only the 4 official failures |
| `--train-days` | Training window before each test month (default 60 days) |

The first seed and the first label set make up the main scenario. The per-event files, the alarm log,
the per-minute status and the final model all come from that scenario.

### How it is evaluated

Walk-forward: each month from April to August 2020 is scored by a model trained only on data from before that month.
The thresholds were fixed before looking at the results: IsolationForest Q3 + 3×IQR on the training scores,
HGB 0.5, cold start 60 minutes. An alarm fires when at least 2/3 of the valid minutes in the last 15 minutes are abnormal.

---

## 4. Output

Everything goes to `anomaly_detection/output/hybrid/`:

| File | Content | In repo? |
|---|---|---|
| `status_walkforward.parquet` | Status for every minute, Apr–Aug 2020. **Use this for dashboard replay** | Yes |
| `hybrid_final.joblib` | Both final models, for data after August 2020 | Yes |
| `grafik/*.png` | 8 charts for the report | Yes |
| `hasil_hybrid.csv` | Summary per method, label set and seed | No, created by `train_hybrid.py` |
| `kejadian_hybrid.csv` | First warning and first red per event | No, created by `train_hybrid.py` |
| `alarm_hybrid.csv` | Log of alarm episodes with sensor values | No, created by `train_hybrid.py` |
| `tradeoff_hybrid.csv` | Other thresholds, only for the trade-off curve | No, created by `train_hybrid.py` |

### Status rules

The rules are checked in order and the first one that matches is used:

| # | Condition | Status |
|---|---|---|
| 1 | No data, frozen sensor, or fewer than 8 valid minutes in the last 15 | Abu-abu (grey) |
| 2 | HGB is active and the HGB alarm is on | Merah (red) |
| 3 | HGB not active yet and the IF alarm has been on for 60+ minutes | Merah (red) |
| 4 | IF alarm is on | Kuning (yellow) |
| 5 | Otherwise | Hijau (green) |

The full column descriptions, in Indonesian, are in
[`anomaly_detection/docs/HYBRID_KELUARAN.md`](anomaly_detection/docs/HYBRID_KELUARAN.md).

---

## 5. Using the final model on new data

```python
import joblib
from anomaly_detection.common.hybrid import score_table

bundle = joblib.load("anomaly_detection/output/hybrid/hybrid_final.joblib")
status = score_table(bundle, new_online_table)  # table must have the columns made by preprocess_dataprep.py
```

**Don't use `hybrid_final.joblib` to replay February–August 2020.** That model was trained on those months,
so red looks like 16/16 events with 0 false alarms. The honest walk-forward result is 14/16 with 5 false alarms.
For a replay, read `status_walkforward.parquet`.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `FileNotFoundError: ... MetroPT3(AirCompressor).csv` | The CSV is missing or in the wrong place. Put it in the repo root with exactly that name (step 1) |
| `FileNotFoundError: ... hasil_hybrid.csv` when making charts | Run `python -m anomaly_detection.anomali.train_hybrid` first |
| `ModuleNotFoundError: No module named 'anomaly_detection'` | Run from the repo root with `python -m anomaly_detection....`, not `python file.py` from inside a subfolder |
| `ImportError: Unable to find a usable engine ... parquet` | `pip install pyarrow` |
| Typing the filename in PowerShell fails | Put the name in quotes, because of the parentheses: `"MetroPT3(AirCompressor).csv"` |
| A row-count check prints `BEDA` | The CSV is incomplete or was edited. Download it again |

---

## 7. RUL model, calibration and analysis

Three scripts build on the hybrid. Details (in Indonesian) are in
[`anomaly_detection/docs/MODEL_KELUARAN.md`](anomaly_detection/docs/MODEL_KELUARAN.md), and the full report is
[`anomaly_detection/output/model/LAPORAN_ANALISIS.md`](anomaly_detection/output/model/LAPORAN_ANALISIS.md).

```bash
python -m anomaly_detection.rul_final.train_baseline          # 1. baseline RUL + anomaly models (Random Forest, XGBoost), first metrics
python -m anomaly_detection.rul_final.train_final_calibrated  # 2. final calibrated models, optimised thresholds, exported to output/model/final/
python -m anomaly_detection.laporan.analysis_report           # 3. FP/FN analysis, ROI in three scenarios, sensitivity, degradation patterns
python -m anomaly_detection.tests.test_model                  # 8 tests of the shared functions
python -m anomaly_detection.rul_final.predict                 # use the exported model on new data
```

Run `train_hybrid` first if `output/hybrid/status_walkforward.parquet` is missing. All choices (model, hyperparameters,
calibration, thresholds) are made inside each training window, never on the test month or segment.

Walk-forward results, April-August 2020:

| | Best baseline | Final |
|---|---|---|
| Anomaly, events detected (red) | 12/16 | 14/16, all 4 official failures |
| Anomaly, false red alarms | 2-7 | 4 (0.18 per week); first hybrid: 5 |
| Anomaly, calibration ECE | 0.0021 | 0.0011 |
| RUL, MAE all rows | 8.7 h | 12.1 h |
| RUL, MAE before failure (0 < RUL < 72 h) | 33.2-35.1 h | 34.7 h |
| RUL, recall of the Critical stage | 0.00 | 0.75 |

6 of 9 targets are met: all five anomaly targets, but three of the four RUL targets fail. The final anomaly model uses the same 9 process
features as the hybrid HGB; with all 51 features it gave 10 false red alarms. That choice was made after comparing
walk-forward results, so confirm it on data after August 2020.
The RUL model cannot warn 24-72 hours ahead: before F1-F3 the sensors look healthy until the
failure starts, so its error before failure is close to a naive "always 72 h" guess (38.2 h). Show RUL as a stage
(Failure / Critical / Warning / Normal) with its interval, not as an hour countdown.
ROI is computed in cost units (1 UB = one planned repair) with the formulas and low / base / high values from the
milestone cost-assumption table.

These results were made with Python 3.14, scikit-learn 1.9.1, xgboost 3.4.1, pandas 3.1.1 and numpy 2.5.5
(the exact versions are saved in `output/model/final/metadata.json`). Other versions give slightly different numbers.
The hybrid result in `output/hybrid/` is 14/16 events with 5 false red alarms. Re-running `train_hybrid` with other
library versions can change it a little (for example 3 false red alarms instead of 5).

---

## Reference

Davari, N., Veloso, B., Ribeiro, R. P., Pereira, P. M., & Gama, J. (2021).
*Predictive maintenance based on anomaly detection using deep learning for air production unit in the railway industry.*
IEEE DSAA 2021. The 16 evaluation events come from Table II of this paper.
