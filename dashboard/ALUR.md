# Alur Data dan Cara Kerja Dashboard

> Dashboard ini memutar ulang hasil analisis historis. Ia tidak menerima aliran sensor langsung dan tidak menjalankan ulang model final untuk setiap titik replay.

## Gambaran singkat

Bayangkan data sensor sebagai catatan perjalanan mesin. Tahap preprocessing merapikan catatan itu, model membaca pola-pola yang sudah dirapikan, lalu laporan merangkum hasilnya. Dashboard memutar kembali data sensor bersama hasil penilaian yang sudah disimpan.

```text
CSV sensor
   ↓
preprocessing → output/dataprep/*.parquet
   ├── anomali → output/hybrid/*
   └── rul_final → output/model/* dan model final
                         ↓
                     laporan → LAPORAN_ANALISIS.md, grafik, tabel
                         ↓
Dashboard: dataset_online_1min.parquet + prediksi_walkforward.parquet
```

## Peran folder

| Folder | Gunanya |
| --- | --- |
| `preprocessing/` | Membersihkan dan mengubah CSV sensor menjadi tabel per menit, fitur, dan label yang dipakai model. Ini dijalankan sebelum pelatihan jika data preprocessing perlu dibuat ulang. |
| `anomali/` | Menyusun dan mengevaluasi status hybrid seperti Hijau, Kuning, Merah, dan Abu-abu. Kode pelatihan walk-forward menggabungkan skor model dengan Isolation Forest serta aturan status. |
| `rul_final/` | Melatih baseline dan model final anomali/RUL, membuat prediksi walk-forward, dan menyediakan `predict.py` untuk memberi skor pada tabel baru yang sudah memiliki fitur preprocessing yang sesuai. |
| `common/` | Fungsi bersama untuk fitur, status hybrid, dan cara mengevaluasi kejadian/alarm. |
| `laporan/` | Mengolah prediksi dan metrik menjadi laporan analisis, grafik, tabel pendukung, dan dasar kalkulator ROI. |
| `tests/` | Memeriksa perilaku kode seperti aturan status dan kalkulasi, bukan folder model atau data dashboard. `run_all` menjalankan tes di awal alurnya. |
| `output/` | Menyimpan artefak hasil preprocessing, model, prediksi, laporan, grafik, dan tabel. Folder ini berisi hasil kerja tahap-tahap di atas. |
| `dashboard/` | FastAPI membaca data dan menyediakan API; React menampilkan tujuh halaman dashboard dan kontrol replay. |

## Urutan kerja dari sensor sampai laporan

1. **Data mentah** berada di CSV MetroPT-3 pada root repository. CSV menyimpan pengukuran sensor menurut waktu.
2. **Preprocessing** mengurutkan data, membuat tabel per menit, membentuk fitur yang hanya menggunakan riwayat masa lalu, dan menyiapkan label. Hasil utamanya berada di `anomaly_detection/output/dataprep/`.
3. **Deteksi anomali** mengevaluasi data secara berurutan menurut waktu. Setiap putaran hanya memakai data yang sudah tersedia sampai saat itu, lalu menilai periode berikutnya. April adalah cold start: model supervised belum aktif.
4. **RUL** memperkirakan sisa jam operasi. Versi terbaru memakai XGBoost sedang; pemilihan modelnya menggunakan validasi expanding-window.
5. **Laporan** membaca hasil evaluasi untuk menghitung metrik, menyusun analisis ROI, dan menulis ringkasan serta grafik ke `anomaly_detection/output/model/`. Perintah utama seluruh tahap ada di `python -m anomaly_detection.run_all` dari root repository.

## Model anomali, hybrid, dan RUL

- **Ensemble anomali** adalah model supervised final yang menggabungkan Random Forest, XGBoost dangkal, dan XGBoost sedang. Model ini memakai 9 fitur proses dan skor akhirnya dikalibrasi dengan isotonic. Ambang tetap pada metadata final adalah 0,70; ambang untuk prediksi walk-forward dapat berbeda menurut bulan.
- **Status hybrid** adalah keputusan status yang dilihat pada dashboard. Sistem hybrid menggunakan skor supervised bersama Isolation Forest dan aturan kondisi. Karena itu, skor anomali dan status Merah berkaitan, tetapi keduanya bukan keluaran yang sama.
- **Walk-forward** adalah cara menguji dengan urutan waktu: model hanya belajar dari masa yang lebih awal, kemudian menilai data setelahnya. File prediksinya menyimpan skor, ambang, status, dan RUL per timestamp.
- **RUL** menghasilkan estimasi sisa jam dan rentang bila tersedia. Hasil validasi terbaru memiliki MAE pra-kegagalan 34,7 jam dan recall Critical 0,75. Validasi belum membuktikan bahwa model memberi peringatan 24–72 jam sebelum gagal, jadi RUL adalah petunjuk kondisi, bukan tanggal pasti penggantian.
- `model_final.joblib` adalah bundel model untuk penilaian tabel baru melalui `rul_final/predict.py`. Dashboard replay tidak memuat bundel ini untuk menghitung ulang setiap menit.

Metrik hybrid walk-forward terbaru mendeteksi 14 dari 16 kejadian dan 4 dari 4 kegagalan resmi, dengan 4 alarm Merah palsu (0,18 per minggu). ECE 0,0011 adalah metrik kalibrasi ensemble. Hasil RUL mencapai 6 dari 9 target proyek, tetapi tidak membuktikan peringatan 24–72 jam sebelum kegagalan.

## Data yang dipakai dashboard

Backend menggabungkan dua berkas menurut timestamp:

| Berkas | Isi dan pemakaian |
| --- | --- |
| `output/dataprep/dataset_online_1min.parquet` | Nilai sensor per menit, seperti TP2, TP3, suhu oli, arus motor, COMP, dan DV_eletric. |
| `output/model/prediksi_walkforward.parquet` | Skor anomali terkalibrasi, ambang per menit, status hybrid, pemicu, status aktif model, serta estimasi RUL dan intervalnya. |
| `output/model/final/metadata.json` | Jenis model final, fitur, metrik walk-forward, dan target validasi untuk ringkasan dashboard. |

Rentang replay mengikuti timestamp prediksi yang tersedia, bukan seluruh rentang data sensor. Data sensor yang tidak memiliki hasil prediksi tetap bisa tersedia, tetapi statusnya Abu-abu dan nilai modelnya kosong. Untuk menilai CSV atau sensor lain, data itu perlu melalui preprocessing dan penilaian model yang sesuai; dashboard saat ini tidak menyediakan unggah data.

## Cara membaca bagian dashboard

- **Ringkasan mesin:** status hybrid, timestamp replay, nilai sensor utama, status aktuator kompresor, dan metrik validasi.
- **Telemetri:** grafik TP2/TP3, suhu oli, dan arus motor. Filter rentang waktu dan brush grafik mengubah bagian waktu yang dilihat.
- **Deteksi anomali:** skor ensemble dibanding ambang pada timestamp tersebut. Ambang berubah per bulan karena tiap putaran walk-forward memakai data latih yang tersedia saat itu. April menunjukkan model supervised belum aktif. ECE 0,0011 menggambarkan kalibrasi skor pada validasi, bukan jaminan peluang gagal pada sensor baru.
- **RUL:** sisa jam, tahap risiko, dan interval bila tersedia. Gunakan sebagai sinyal inspeksi bersama sensor dan status.
- **Notifikasi dan log insiden:** rekaman historis ditampilkan sebagai simulasi replay. Email dan WhatsApp Bot adalah contoh pesan; tidak ada pengiriman sungguhan.
- **Biaya & ROI:** membandingkan biaya asumsi strategi reaktif, preventif, dan prediktif. Nilai input dan grafik dalam UB; ilustrasi konversi adalah 1 UB = Rp50 juta. Asumsi dasar disimpan di `dashboard/backend/app/core/roi_defaults.py` dan disalin dari laporan terbaru. ROI laporan memakai definisi alarm palsu 0,78 episode/minggu yang memasukkan alarm Merah pada kejadian kecil. Angka 0,18/minggu pada metrik hybrid memakai hitungan alarm yang lebih sempit. Jika asumsi laporan berubah, konfigurasi dashboard harus diperbarui agar hasil tetap cocok. Nilai rupiah dan ROI merupakan simulasi, bukan catatan biaya aktual.

## Hasil yang dibuat otomatis

- `output/dataprep/*.parquet`: tabel sensor dan fitur hasil preprocessing.
- `output/hybrid/`: artefak status hybrid dan visualisasi terkait.
- `output/model/final/model_final.joblib` dan `metadata.json`: bundel model final serta informasi model dan validasinya.
- `output/model/prediksi_walkforward.parquet`: deret prediksi yang dipakai untuk replay dashboard.
- `output/model/LAPORAN_ANALISIS.md`, `output/model/grafik/`, dan tabel `analisis_*.csv`: laporan, grafik, dan tabel pendukung.

Dashboard hanya membaca hasil-hasil tersebut. Menjalankan dashboard tidak menjalankan ulang preprocessing, pelatihan, prediksi model, maupun pembuatan laporan.
