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
python -m anomaly_detection.tests.test_model
python -m anomaly_detection.tests.test_roi                     # uji rumus ROI
python -m anomaly_detection.rul_final.predict                 # uji teknis model yang diekspor
```

Atau semuanya sekaligus: `python -m anomaly_detection.run_all`.

Butuh `xgboost` selain paket di README utama: `pip install xgboost`.

## Ringkasan hasil (walk-forward April-Agustus 2020)

| | Baseline terbaik | Final |
|---|---|---|
| Anomali, kejadian terdeteksi (Merah) | 12/16 (RF/XGBoost, April tanpa model) | 14/16, 4/4 kegagalan resmi |
| Anomali, alarm palsu Merah | 2 (RF) - 7 (XGBoost) | 4 (0,18/minggu); hybrid versi awal: 5 |
| Anomali, Brier skor Mei-Agu | 0,0019 (XGBoost) | 0,0013 |
| Anomali, ECE (kalibrasi) | 0,0021 (skor mentah) | 0,0011 |
| RUL, MAE semua baris | 8,7 jam (RF) | 12,1 jam |
| RUL, MAE pra-failure (0 < RUL < 72 jam) | 33,2 jam (XGBoost) - 35,1 jam (RF) | 34,7 jam |
| RUL, recall tahap Critical | 0,00 | 0,75 |

6 dari 9 target lulus; semua target anomali lulus, tiga target RUL tidak.

Anomali: model supervised final memakai 9 fitur proses yang sama dengan HGB di sistem hybrid. Dengan 51 fitur, alarm
palsu Merah 10; dengan 9 fitur 4, deteksi sama (14/16). Keputusan 9 fitur ini diambil setelah membandingkan hasil
walk-forward yang sama (seperti pilihan 9 fitur HGB tim), jadi angkanya sedikit optimistis dan perlu dikonfirmasi pada
data sesudah Agustus 2020.

RUL: pada jendela pra-failure, model final (34,7 jam MAE) setara dengan baseline (33,2-35,1 jam) dan hanya sedikit
mengungguli tebakan naif RUL tetap 72 jam (38,2 jam). Tidak ada kegagalan yang diperingatkan sebelum mulai, karena
sensor sebelum F1-F3 tidak menunjukkan gejala. Percobaan tambahan tidak mengubah ini: override dari status Merah hybrid
memberi hasil yang sama, dan fitur riwayat 72 jam / 7 hari hanya memperbaiki MAE semua baris (12,1 menjadi 9,1 jam)
sementara MAE pra-failure memburuk (35,0 jam), sehingga tidak dipakai. Keunggulan model final ada pada tahap Critical
(recall 0,75), yang berasal dari override Failure model anomali. Dengan hanya empat kegagalan resmi, RUL belum layak
dipakai sebagai janji penggantian 24-72 jam sebelumnya. Cakupan interval pra-failure hanya 23,5%.

## Cara kerja model final

Anomali (per bulan uji):
1. Validasi dalam GroupKFold per kelompok kejadian (kejadian berjarak < 3 hari satu kelompok). Fitur: 9 fitur proses
   (`ANOMALY_FEATURES`, sama dengan HGB).
2. Pilih kandidat: XGBoost dangkal, XGBoost sedang, Random Forest, atau ensemble ketiganya.
3. Kalibrasi isotonic dari skor out-of-fold.
4. Ambang dengan biaya terkecil: 10 x kejadian terlewat + alarm palsu (`--cost-ratio`).
5. Skor terkalibrasi menggantikan HGB di aturan status hybrid. April tetap memakai cold start IsolationForest.

RUL (per segmen uji, segmen k = periode menuju kegagalan k):
1. Validasi expanding-window: segmen berikutnya hanya diuji memakai segmen terdahulu; saat baru satu segmen tersedia,
   blok waktu diuji berurutan dan hanya dilatih dengan blok sebelumnya.
2. Pilih hiperparameter XGBoost berdasar MAE pra-failure (0 < RUL < 72 jam), bukan MAE menit sehat yang mendominasi.
3. Kalibrasi isotonic prediksi ke RUL nyata.
4. RUL = 0 saat model anomali menyatakan pola kegagalan (override Failure).
5. Interval 80% conformal Mondrian.
6. Ambang alarm RUL dari validasi dalam (biaya yang sama dengan anomali).

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
| `rul_prognostik` | RUL dari regresi + isotonic, tanpa override; belum terbukti memberi lead-time |
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
4. **ROI memakai UB sesuai tabel asumsi biaya pada milestone:** 1 UB adalah biaya perbaikan terencana. `ROI_SCENARIOS`
   menyajikan batas rendah, nilai dasar, dan batas tinggi. Frekuensi kegagalan dan durasi downtime belum ditetapkan
   dalam tabel, sehingga laporan memakai frekuensi 4 kegagalan/7 bulan dan durasi label kegagalan rata-rata sebagai
   proksi yang harus diganti bila data operasional tersedia.
5. **TP/FN/FP ROI dihitung dari validasi walk-forward, bukan LOFO.** Alasannya untuk mencegah pelatihan memakai data
   masa depan; laporan menandai ini sebagai perbedaan metode dari dokumen. ROI dihitung per tahun sebagai
   penghematan terhadap strategi reaktif atau preventif dibagi biaya sistem tahunan. Sumbernya status Merah sistem
   hybrid final (`status_final` di `prediksi_walkforward.parquet`). FP di ROI adalah setiap episode Merah yang tidak
   menyentuh kegagalan resmi, termasuk alarm pada kejadian kecil, karena masing-masing tetap memicu satu inspeksi.
