# Model RUL, kalibrasi, dan analisis

Tiga tahap, masing-masing satu skrip. Semua hasil ada di `anomaly_detection/output/model/`.

| Tahap | Skrip | Hasil utama |
|---|---|---|
| 1. Model baseline tervalidasi | `rul_final/train_baseline.py` | `baseline_anomali.csv`, `baseline_rul.csv`, `baseline_metrik.json` |
| 2. Model final terkalibrasi | `rul_final/train_final_calibrated.py` | `final_target.csv`, `prediksi_walkforward.parquet`, `final/model_final.joblib` |
| 3. Laporan analisis dan insight | `laporan/analysis_report.py` | [`LAPORAN_ANALISIS.md`](../output/model/LAPORAN_ANALISIS.md), `grafik/*.png` |

## Cara menjalankan

Jalankan dari root repo:

```
python -m anomaly_detection.anomali.train_hybrid              # sekali, jika status_walkforward.parquet belum ada
python -m anomaly_detection.rul_final.train_baseline          # sekitar 4 menit
python -m anomaly_detection.rul_final.train_final_calibrated  # sekitar 6 menit
python -m anomaly_detection.laporan.analysis_report           # sekitar 1 menit
python -m anomaly_detection.tests.test_model                  # 8 uji fungsi bersama
python -m anomaly_detection.rul_final.predict                 # uji teknis model yang diekspor
```

Atau semuanya sekaligus: `python -m anomaly_detection.run_all`.

Butuh `xgboost` selain paket di README utama: `pip install xgboost`.

## Ringkasan hasil (walk-forward April-Agustus 2020)

| | Baseline terbaik | Final |
|---|---|---|
| Anomali, kejadian terdeteksi (Merah) | 12/16 (RF/XGBoost, April tanpa model) | 14/16, 4/4 kegagalan resmi |
| Anomali, alarm palsu Merah | 2 (RF) - 7 (XGBoost) | 10 (0,46/minggu) |
| Anomali, ECE (kalibrasi) | 0,0021 (skor mentah) | 0,0030 |
| RUL, MAE semua baris | 8,6 jam (RF) | 7,8 jam |
| RUL, MAE jendela degradasi | 41,4 jam (XGBoost) | 26,4 jam |
| RUL, recall tahap Critical | 0,00 | 0,78 |

6 dari 9 target lulus. Yang tidak lulus beserta alasannya ada di laporan bagian 1.3. Ringkasnya, RUL 24-72 jam
sebelum kegagalan tidak dapat dicapai karena F1-F3 tidak menunjukkan gejala sebelum label.

## Cara kerja model final

Anomali (per bulan uji):
1. Validasi dalam GroupKFold per kelompok kejadian (kejadian berjarak < 3 hari satu kelompok).
2. Pilih kandidat: XGBoost dangkal, XGBoost sedang, Random Forest, atau ensemble ketiganya.
3. Kalibrasi isotonic dari skor out-of-fold.
4. Ambang dengan biaya terkecil: 10 x kejadian terlewat + alarm palsu (`--cost-ratio`).
5. Skor terkalibrasi menggantikan HGB di aturan status hybrid. April tetap memakai cold start IsolationForest.

RUL (per segmen uji, segmen k = periode menuju kegagalan k):
1. XGBoost regresi, hiperparameter dari validasi dalam leave-one-segment-out.
2. Kalibrasi isotonic prediksi ke RUL nyata.
3. RUL = 0 saat model anomali menyatakan pola kegagalan (override Failure).
4. Interval 80% conformal Mondrian.
5. Ambang alarm RUL dari validasi dalam (biaya yang sama dengan anomali).

## `prediksi_walkforward.parquet`

Satu baris per menit data_ok di luar zona grace, April-Agustus 2020. Untuk replay dashboard yang jujur.

| Kolom | Isi |
|---|---|
| `p_xgb_mentah` | Skor model terpilih sebelum kalibrasi |
| `p_terkalibrasi` | Skor sesudah kalibrasi isotonic, 0-1 |
| `ambang_anomali` | Ambang bulan itu (dipilih dari data latih) |
| `model_aktif` | False di April (belum ada label) |
| `status_final`, `pemicu_final` | Status hybrid dengan model final |
| `status_lama` | Status hybrid lama (HGB 0,5), untuk pembanding |
| `rul_prognostik` | RUL dari regresi + isotonic, tanpa override |
| `rul_pred` | RUL final (0 saat pola kegagalan) |
| `rul_bawah`, `rul_atas` | Interval 80% |
| `rul_ambang` | Ambang alarm RUL segmen itu |

Kolom RUL kosong untuk menit di luar segmen uji 2-5 (April sebelum F1).

## `final/model_final.joblib`

Model untuk data sesudah Agustus 2020. Pakai lewat `predict.score_table`. Kunci utama:

| Kunci | Isi |
|---|---|
| `iforest`, `if_threshold`, `if_features`, `medians` | IsolationForest (resep sama dengan `hybrid_final.joblib`) |
| `anomaly_members`, `anomaly_calibrator`, `anomaly_threshold` | Model anomali, kalibrator isotonic, ambang |
| `rul_model`, `rul_isotonic`, `rul_conformal`, `rul_alert_hours` | Model RUL, kalibrasi, interval, ambang alarm |

`final/metadata.json` berisi fitur, ambang, kuantil conformal, versi pustaka, dan metrik walk-forward.
`final/rul_xgb.json` (dan `anomali_*.json` jika model anomali terpilih XGBoost) adalah model dalam format asli XGBoost.

## Aturan yang wajib diikuti

1. **Jangan menilai `model_final.joblib` pada Februari-Agustus 2020.** Model itu sudah melihat data tersebut. Pakai `prediksi_walkforward.parquet`.
2. **Tampilkan RUL sebagai tahap dan interval**, bukan hitung mundur jam. Model belum bisa memperingatkan 24-72 jam sebelumnya.
3. **`p_terkalibrasi` boleh ditampilkan sebagai perkiraan peluang** (berbeda dengan `hgb_score` hybrid lama), tetapi tetap berdasarkan 16 kejadian saja.
4. **Angka ROI di laporan adalah asumsi.** Ganti `ROI_SCENARIOS` di `analysis_report.py` dengan data biaya nyata, lalu jalankan ulang.
