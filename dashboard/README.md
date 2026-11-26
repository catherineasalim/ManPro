# MetroPT-3 Maintenance Dashboard

Dashboard demo untuk memantau data telemetri kompresor Metro do Porto, mengeksplorasi status anomali dan RUL, melihat simulasi notifikasi, serta membandingkan biaya strategi perawatan.

Dashboard berjalan lokal dan menggunakan **replay data historis**. Tidak ada koneksi sensor real-time, unggah CSV, atau pengiriman email/WhatsApp sungguhan.

**[Baca ALUR.md](ALUR.md)** untuk penjelasan sederhana tentang peran folder, alur data dan model, cara kerja replay, serta asal keluaran dashboard.

## Isi dashboard

Navigasi dashboard terdiri dari tujuh halaman:

1. **Ringkasan mesin** — status pada posisi replay, nilai sensor utama, sinyal aktuator, dan ringkasan validasi model.
2. **Telemetri** — grafik TP2, TP3, suhu oli, dan arus motor dengan filter waktu dan zoom.
3. **Deteksi anomali** — skor terkalibrasi, status, pemicu, dan penjelasan tiap level.
4. **Remaining useful life** — RUL dalam jam/hari, tahap risiko, dan rentang perkiraan jika tersedia.
5. **Notifikasi** — pratinjau simulasi pesan email dan WhatsApp Bot untuk status Merah saja, satu pesan per episode Merah (jeda penggabungan 30 menit). Kuning tidak dikirim dan hanya tampil di log insiden, sesuai laporan.
6. **Log insiden** — episode alarm beserta durasi, pemicu, dan cuplikan sensor.
7. **Biaya & ROI** — kalkulator asumsi biaya reaktif, preventif, dan prediktif, beserta sensitivitas dan titik impas.

Kontrol replay di bagian atas halaman menyediakan play/pause, pemilihan timestamp, dan kecepatan 1×, 10×, 60×, 200×, 300×, 500×, atau 1000×. Angka kecepatan menunjukkan berapa menit replay yang maju setiap detik waktu demo.

## Sumber data dan batas model

Backend membaca artefak yang sudah ada di repo:

| Berkas | Kegunaan |
| --- | --- |
| `anomaly_detection/output/dataprep/dataset_online_1min.parquet` | Nilai sensor dan status kualitas data per menit |
| `anomaly_detection/output/model/prediksi_walkforward.parquet` | Status, pemicu, skor anomali terkalibrasi, dan RUL dari validasi maju-waktu |
| `anomaly_detection/output/model/final/metadata.json` | Jenis model, fitur, dan metrik walk-forward untuk ringkasan model |

Prediksi *walk-forward* dipakai untuk replay karena model final telah dilatih menggunakan data Februari–Agustus 2020. Memutar ulang rentang yang sama dengan model final akan memberi evaluasi yang terlalu optimistis. Rentang replay mengikuti timestamp prediksi yang tersedia; nilai RUL kosong tetap ditampilkan sebagai belum tersedia.

Model anomali final adalah ensemble Random Forest dan dua konfigurasi XGBoost, memakai 9 fitur proses dan kalibrasi isotonic. Skor ensemble merupakan salah satu masukan status hybrid; status Merah tidak ditentukan oleh skor itu saja. Pada walk-forward, status hybrid mendeteksi 14/16 kejadian termasuk 4/4 kegagalan resmi, dengan 4 alarm Merah palsu atau 0,18 per minggu. ECE 0,0011 adalah metrik kalibrasi model ensemble. Ambang bulanan pada replay adalah April 1,00 (model supervised belum aktif), Mei 0,45, Juni 0,90, Juli 0,65, dan Agustus 0,70.

RUL memakai XGBoost sedang yang dipilih melalui validasi expanding-window. MAE pra-kegagalan 34,7 jam dan recall tahap Critical 0,75; 6 dari 9 target proyek tercapai. RUL dibatasi hingga 72 jam, dan validasi belum membuktikan kemampuan memberi peringatan 24–72 jam sebelum kegagalan. Tampilkan RUL sebagai perkiraan tahap dan rentang, bukan waktu penggantian yang pasti.

ROI memakai asumsi deteksi dan skenario biaya yang disalin dari laporan terbaru ke konfigurasi dashboard di `backend/app/core/roi_defaults.py`. Laporan menghitung 0,78 alarm Merah palsu per minggu untuk ROI karena definisinya juga mencakup episode Merah pada kejadian kecil; angka 0,18 di ringkasan walk-forward menghitung alarm palsu dengan definisi yang lebih sempit. Kalkulator menampilkan biaya dalam UB dan ilustrasi rupiah dengan asumsi 1 UB = Rp50 juta. Pada skenario dasar, ROI acuan laporan adalah 8.365,6% terhadap reaktif dan 1.916,6% terhadap preventif. Jika asumsi laporan berubah, konfigurasi dashboard perlu disinkronkan. Nilai rupiah adalah ilustrasi, bukan biaya operasional aktual.

## Prasyarat

- Python 3.12 atau lebih baru.
- Node.js 20 atau lebih baru dan npm.
- Berkas Parquet pada tabel di atas harus tersedia. Berkas preprocessed sudah disertakan di repo; CSV mentah tidak dibutuhkan untuk menjalankan dashboard.

## Menjalankan di Windows PowerShell

Buka dua terminal dari root repository.

### 1. FastAPI backend

```powershell
conda activate dtsc
cd dashboard/backend
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`dtsc` adalah contoh nama environment Conda; ganti jika environment-mu berbeda. Jika paket backend sudah ada di environment, langkah `pip install` dapat dilewati. API berjalan di `http://127.0.0.1:8000`; dokumentasi interaktif tersedia di `http://127.0.0.1:8000/docs`.

### 2. React frontend

Di terminal kedua:

```powershell
cd dashboard/frontend
Copy-Item .env.example .env
npm.cmd install
npm.cmd run dev
```

Buka alamat yang ditampilkan Vite, biasanya `http://127.0.0.1:5173`. Untuk terminal yang mengizinkan skrip npm PowerShell, `npm` dapat dipakai sebagai pengganti `npm.cmd`.

### Build dan tes

```powershell
cd dashboard/backend
conda activate dtsc
python -m pytest

cd ..\frontend
npm.cmd test
npm.cmd run build
```

Build frontend menghasilkan berkas statis di `dashboard/frontend/dist/`.

## Struktur proyek

```text
dashboard/
├── README.md
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # FastAPI, CORS, dan pendaftaran route
│   │   ├── api/routes/             # Endpoint health, replay, telemetri, alarm, ROI
│   │   ├── core/config.py          # Path artefak dan konfigurasi lingkungan
│   │   ├── schemas/models.py        # Skema request/response Pydantic
│   │   └── services/               # Pembacaan data, replay, alarm, ROI
│   └── tests/                      # Tes logika layanan backend
└── frontend/
    ├── .env.example
    ├── components.json             # Konfigurasi komponen shadcn/ui
    ├── package.json
    └── src/
        ├── app/                    # Routing dan state replay bersama
        ├── components/charts/      # Grafik shadcn/Recharts
        ├── components/shared/      # Panel, badge status, intro halaman
        ├── components/ui/          # Wrapper chart bergaya shadcn/ui
        ├── features/               # Tujuh halaman fitur dashboard
        ├── lib/                    # Klien API dan utilitas tampilan
        └── types/                  # Tipe respons API
```

## API

Semua endpoint berada di bawah `/api`.

| Method | Endpoint | Fungsi |
| --- | --- | --- |
| `GET` | `/health` | Status API dan ketersediaan data |
| `GET` | `/replay/metadata` | Rentang waktu, sinyal tersedia, ringkasan model, metrik walk-forward, dan ambang per bulan |
| `GET` | `/replay/frame?timestamp=...` | Status, sensor, skor, dan RUL pada satu menit |
| `GET` | `/telemetry?start=...&end=...&signals=TP2&signals=TP3` | Data grafik dengan batas jumlah titik |
| `GET` | `/alarms?through=...` | Episode alarm hingga posisi replay |
| `GET` | `/notifications?through=...` | Notifikasi simulasi hingga posisi replay |
| `POST` | `/roi/calculate` | Biaya, ROI, sensitivitas, dan titik impas |

Contoh request kalkulator:

```json
{
  "scenario": "Dasar",
  "costs": {
    "biaya_downtime_per_jam": 0.75,
    "biaya_sistem": 1.2
  }
}
```

Frontend membaca URL API dari `VITE_API_URL` (default `http://127.0.0.1:8000/api`). Backend membaca `DASHBOARD_CORS_ORIGINS` (default mengizinkan `localhost:5173` dan `127.0.0.1:5173`) dan `DASHBOARD_API_PREFIX` dari `.env`.

## Troubleshooting

| Gejala | Yang perlu dicek |
| --- | --- |
| API melaporkan data tidak ditemukan | Jalankan backend dari folder `dashboard/backend`; pastikan tiga artefak data pada tabel sumber ada di repo. |
| `Unable to find a usable engine` atau error Parquet | Pastikan instalasi backend selesai dan `pyarrow` terpasang lewat `pip install -r requirements.txt`. |
| Frontend menampilkan API offline | Jalankan Uvicorn pada port 8000 dan cocokkan `VITE_API_URL` di `frontend/.env`. |
| Error CORS | Pastikan `DASHBOARD_CORS_ORIGINS` memuat origin Vite yang sedang dipakai, biasanya `http://localhost:5173` atau `http://127.0.0.1:5173`. |
| Grafik kosong pada awal/akhir rentang | Sebagian output model atau RUL memang tidak tersedia pada setiap menit. Pilih timestamp dalam rentang prediksi di bar replay. |
| `npm` ditolak PowerShell | Gunakan `npm.cmd` seperti pada langkah instalasi Windows. |

Dashboard tidak menjalankan ulang preprocessing, pelatihan model, atau laporan. Untuk membuat ulang artefak model, ikuti README utama repository.
