# MetroPT-3 Maintenance Dashboard

Dashboard demo untuk memantau data telemetri kompresor Metro do Porto, mengeksplorasi status anomali dan RUL, melihat simulasi notifikasi, serta membandingkan biaya strategi perawatan.

Dashboard berjalan lokal dan menggunakan **replay data historis**. Tidak ada koneksi sensor real-time, unggah CSV, atau pengiriman email/WhatsApp sungguhan.

## Isi dashboard

Navigasi dashboard terdiri dari tujuh halaman:

1. **Ringkasan mesin** — status pada posisi replay, nilai sensor utama, sinyal aktuator, dan ringkasan validasi model.
2. **Telemetri** — grafik TP2, TP3, suhu oli, dan arus motor dengan filter waktu dan zoom.
3. **Deteksi anomali** — skor terkalibrasi, status, pemicu, dan penjelasan tiap level.
4. **Remaining useful life** — RUL dalam jam/hari, tahap risiko, dan rentang perkiraan jika tersedia.
5. **Notifikasi** — pratinjau simulasi pesan email dan WhatsApp Bot saat status naik ke Kuning atau Merah.
6. **Log insiden** — episode alarm beserta durasi, pemicu, dan cuplikan sensor.
7. **Biaya & ROI** — kalkulator asumsi biaya reaktif, preventif, dan prediktif, beserta sensitivitas dan titik impas.

Kontrol replay di bagian atas halaman menyediakan play/pause, pemilihan timestamp, dan kecepatan 1×, 10×, atau 60×. Satu detik waktu demo memajukan replay masing-masing satu, sepuluh, atau enam puluh menit.

## Sumber data dan batas model

Backend membaca artefak yang sudah ada di repo:

| Berkas | Kegunaan |
| --- | --- |
| `anomaly_detection/output/dataprep/dataset_online_1min.parquet` | Nilai sensor dan status kualitas data per menit |
| `anomaly_detection/output/model/prediksi_walkforward.parquet` | Status, pemicu, skor anomali terkalibrasi, dan RUL dari validasi maju-waktu |
| `anomaly_detection/output/model/final/metadata.json` | Metrik walk-forward untuk asumsi deteksi pada kalkulator ROI |

Prediksi *walk-forward* dipakai untuk replay karena model final telah dilatih menggunakan data Februari–Agustus 2020. Memutar ulang rentang yang sama dengan model final akan memberi evaluasi yang terlalu optimistis. Rentang replay mengikuti timestamp prediksi yang tersedia; nilai RUL kosong tetap ditampilkan sebagai belum tersedia.

Skor anomali adalah sinyal model yang dikalibrasi dari jumlah kejadian yang terbatas. RUL dibatasi hingga 72 jam, dan validasi belum membuktikan kemampuan memberi peringatan 24–72 jam sebelum kegagalan. Tampilkan RUL sebagai perkiraan tahap dan rentang, bukan waktu penggantian yang pasti.

ROI menggunakan unit biaya UB dan asumsi skenario yang sama dengan analisis proyek. Metrik deteksi berasal dari hasil walk-forward dan ditampilkan sebagai dasar perhitungan. Biaya dapat diubah di dashboard; angka yang dihasilkan tetap simulasi, bukan biaya operasional aktual.

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
| `GET` | `/replay/metadata` | Rentang waktu, jumlah baris, sinyal tersedia |
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
