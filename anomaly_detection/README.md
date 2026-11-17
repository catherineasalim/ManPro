# Peta folder `anomaly_detection/`

Semua perintah dijalankan dari **root repo** (folder yang berisi README.md utama) dengan `python -m`.
Untuk menjalankan semuanya sekaligus:

```
python -m anomaly_detection.run_all
```

## Alur kerja

```
CSV mentah ──► preprocessing/ ──► output/dataprep/*.parquet
                                      │
                    ┌─────────────────┴──────────────────┐
                    ▼                                    ▼
               anomali/                              rul_final/
       (sistem hybrid: Hijau/Kuning/Merah)   (baseline, model final terkalibrasi, RUL)
          ──► output/hybrid/                   ──► output/model/
                    └─────────────────┬──────────────────┘
                                      ▼
                                  laporan/
                       ──► output/model/LAPORAN_ANALISIS.md
```

## Isi tiap folder

| Folder | File | Fungsinya | Dijalankan langsung? |
|---|---|---|---|
| `preprocessing/` | `preprocess_dataprep.py` | **Utama.** CSV mentah menjadi tabel per menit dengan 51 fitur dan label | Ya, hanya jika ingin membuat ulang dari CSV |
| | `preprocess_iforest.py` | Pipeline lama. Masih menyimpan konstanta bersama: 16 kejadian (`EVENTS`), putaran bulan (`FOLDS`), margin, lokasi CSV dan output | Tidak |
| | `preprocess_supervised.py` | Pipeline lama untuk model supervised. Menyimpan `LABEL_COVERAGE` | Tidak |
| `anomali/` | `train_hybrid.py` | **Utama.** Melatih dan menilai sistem hybrid, menulis `output/hybrid/` | Ya |
| | `visualize_hybrid.py` | 8 grafik hybrid | Ya, sesudah `train_hybrid` |
| | `model_iforest.py`, `model_supervised.py` | Resep model IsolationForest dan HGB/RF/LR | Tidak (versi lama bisa dijalankan, butuh CSV) |
| | `train_iforest_dataprep.py`, `train_hgb_dataprep.py` | Uji masing-masing model sendiri. Fungsinya dipakai `train_hybrid` | Opsional |
| `rul_final/` | `train_baseline.py` | Deliverable 1: baseline Random Forest dan XGBoost untuk anomali dan RUL | Ya |
| | `train_final_calibrated.py` | Deliverable 2: model final terkalibrasi, ambang teroptimasi, diekspor | Ya, sesudah `train_baseline` |
| | `predict.py` | Memakai model final untuk data baru | Ya |
| `laporan/` | `analysis_report.py` | Deliverable 3: FP/FN, ROI tiga skenario, sensitivitas, pola degradasi | Ya, sesudah `train_final_calibrated` |
| `common/` | `evaluation.py` | Cara menilai alarm (per kejadian, alarm palsu, delay). Dipakai semua model | Tidak |
| | `hybrid.py` | Aturan status Hijau/Kuning/Merah/Abu-abu | Tidak |
| | `model_utils.py` | Fungsi bersama model RUL dan anomali (metrik, data latih, folder output) | Tidak |
| `tests/` | `test_hybrid.py`, `test_model.py` | Unit test (13 + 8) | Ya |
| `docs/` | `HYBRID_KELUARAN.md` | Arti setiap kolom output hybrid (untuk tim dashboard) | - |
| | `MODEL_KELUARAN.md` | Arti setiap output model RUL dan model final | - |

## Output yang penting

| File | Isi |
|---|---|
| `output/model/LAPORAN_ANALISIS.md` | **Baca ini dulu.** Laporan lengkap dengan tabel dan grafik |
| `output/model/grafik/*.png` | 9 grafik laporan |
| `output/model/final/model_final.joblib` | Model final untuk data baru (dipakai `rul_final/predict.py`) |
| `output/model/prediksi_walkforward.parquet` | Skor, status, dan RUL per menit April-Agustus 2020, untuk replay dashboard |
| `output/hybrid/status_walkforward.parquet` | Status hybrid per menit (versi tim sebelumnya) |
| `output/hybrid/grafik/*.png` | 8 grafik hybrid |
| `output/dataprep/*.parquet` | Tabel hasil preprocessing, input semua model |

File `*.csv` di `output/` tidak ikut di repo (`.gitignore`), jadi dibuat ulang saat skrip dijalankan.

## Urutan membaca kode

1. `docs/MODEL_KELUARAN.md` dan `output/model/LAPORAN_ANALISIS.md`: apa hasilnya.
2. `common/evaluation.py`: bagaimana alarm dinilai.
3. `anomali/train_hybrid.py`: sistem hybrid.
4. `rul_final/train_final_calibrated.py`: model final dan RUL.
