# Laporan Proyek: Pemeliharaan Prediktif Kompresor Udara Kereta Metro

**Proyek ManPro Kelompok 20**
Dataset: MetroPT-3, unit produksi udara (APU) kereta Metro do Porto, Februari-Agustus 2020

---

## Ringkasan

Proyek ini membangun sistem pemantauan kompresor udara yang mendeteksi anomali dan memperkirakan sisa umur
pakai (Remaining Useful Life, RUL). Hasil utama, diukur dengan validasi walk-forward April-Agustus 2020:

- Sistem final mendeteksi **14/16 kejadian** dan **4/4 kegagalan resmi** dengan alarm Merah, dengan delay median
  11 menit. Alarm palsu Merah tercatat 4 kali dalam 22 minggu (0,18 per minggu).
- Skor anomali sudah terkalibrasi (ECE 0,0011), sehingga bisa dibaca sebagai perkiraan peluang.
- MAE semua baris RUL adalah 12,1 jam, tetapi MAE pra-failure
  34,7 jam dibanding baseline sederhana RUL tetap 72 jam
  (38,2 jam). Tidak ada kegagalan yang diperingatkan sebelumnya pada validasi walk-forward;
  MAE semua baris didominasi menit sehat dan tidak membuktikan kemampuan prediksi dini.
- 6 dari 9 target metrik tercapai.
- Pada nilai dasar, ROI prediktif adalah 8.365,6% terhadap reaktif dan
  1.916,6% terhadap preventif, berdasarkan biaya tahunan dalam UB. Dengan ilustrasi
  1 UB = Rp 50 juta, penghematan per unit APU per tahun sekitar Rp 4,18 miliar terhadap reaktif dan
  Rp 958 juta terhadap preventif.
  ROI terhadap reaktif positif pada: Batas rendah, Dasar, Batas tinggi.
- Insight terpenting: setiap kegagalan resmi didahului kejadian kecil dalam 2-7 hari, sehingga kejadian kecil layak
  dijadikan pemicu inspeksi.

---

## 1. Pendahuluan

### 1.1 Latar belakang

Kompresor udara (Air Production Unit, APU) menyuplai udara bertekanan untuk rem, suspensi, dan pintu kereta.
Kegagalan APU di tengah operasi membuat kereta harus ditarik dari layanan dan mengganggu jadwal. Selama ini
pemeliharaan dilakukan secara terjadwal atau sesudah kerusakan terjadi. Data sensor yang sudah tersedia memberi
peluang untuk mendeteksi masalah lebih awal.

### 1.2 Tujuan

1. Membangun model baseline untuk deteksi anomali dan RUL, lalu mengukur kinerjanya.
2. Mengembangkan model final yang terkalibrasi, dengan ambang yang dioptimasi, dan siap dipakai pada data baru.
3. Menganalisis kesalahan model, nilai bisnisnya, sensitivitas terhadap asumsi, serta pola degradasi mesin.

### 1.3 Ruang lingkup

Satu unit APU, data Februari-Agustus 2020. Analisis biaya memakai asumsi karena dataset tidak memuat data biaya.

---

## 2. Data

| Aspek | Keterangan |
|---|---|
| Sumber | MetroPT-3 (UCI Machine Learning Repository), 1.516.948 baris, interval 10 detik |
| Sensor | 7 analog (tekanan, suhu oli, arus motor) dan 8 digital |
| Agregasi | Rata-rata per menit, 51 fitur yang hanya melihat ke belakang (jendela 15, 60, dan 360 menit) |
| Label anomali | 16 kejadian dari Tabel II Davari dkk. (2021), termasuk 4 kegagalan resmi (F1-F4) |
| Label RUL | Jam menuju awal kegagalan resmi berikutnya, dibatasi 72 jam |
| Data dikecualikan | Sensor beku, data kosong, dan masa antara kegagalan dan perbaikan |

Persiapan data mengikuti pipeline yang sudah ada di proyek ini (`preprocess_dataprep.py`).

---

## 3. Metodologi

### 3.1 Skema validasi

Data deret waktu tidak boleh dibagi acak, karena menit yang berdekatan hampir identik. Proyek ini memakai
**validasi walk-forward**: setiap bulan (anomali) atau segmen menuju kegagalan (RUL) diuji oleh model yang hanya
dilatih dengan data sebelumnya. Semua pilihan model, kalibrasi, dan ambang ditentukan dari data latih, tidak pernah
dari data uji.

Kejadian dinilai per kejadian: kejadian dianggap terdeteksi jika ada alarm antara 2 jam sebelum mulai sampai akhir
kejadian. Alarm palsu adalah episode alarm yang tidak menyentuh kejadian mana pun.

### 3.2 Model baseline

- **Anomali**: Random Forest dan XGBoost, 51 fitur, ambang 0,5, tanpa penyetelan.
- **RUL**: Random Forest dan XGBoost regresi, alarm jika prediksi RUL di bawah 24 jam.

### 3.3 Model final

**Deteksi anomali**
1. Kandidat: XGBoost dangkal, XGBoost sedang, Random Forest, dan rata-rata ketiganya (ensemble).
2. Validasi dalam dengan GroupKFold per kelompok kejadian, untuk memilih kandidat.
3. Kalibrasi isotonic, sehingga skor 0,8 berarti sekitar 80% menit dengan skor itu memang kejadian.
4. Ambang dipilih dengan biaya terkecil, dengan asumsi satu kejadian terlewat setara 10 alarm palsu.
5. Skor terkalibrasi dipakai dalam aturan status hybrid (Hijau/Kuning/Merah/Abu-abu). Pada April, saat belum ada
   label, IsolationForest menangani peringatan (aturan cold start).

**RUL**
1. XGBoost regresi, hiperparameter dipilih dengan validasi expanding-window yang hanya memakai data masa lalu.
2. Kalibrasi isotonic untuk menghapus bias prediksi.
3. Saat model anomali mendeteksi pola kegagalan, RUL ditetapkan 0 (tahap Failure).
4. Interval prediksi 80% dengan metode conformal.

### 3.4 Target metrik

Target ditetapkan setelah melihat hasil baseline, sebelum model final dijalankan:

| Area | Metrik | Target |
|---|---|---|
| Anomali | Hybrid Merah: kejadian terdeteksi | ≥ 14 |
| Anomali | Hybrid Merah: kegagalan resmi terdeteksi | ≥ 4 |
| Anomali | Hybrid Merah: alarm palsu per minggu | ≤ 0,25 |
| Anomali | Model terkalibrasi: Brier skor Mei-Agu | ≤ 0,0019 |
| Anomali | Model terkalibrasi: ECE Mei-Agu | ≤ 0,05 |
| RUL | MAE sebelum failure (jam) | ≤ 12,0 |
| RUL | Cakupan interval 80% | 0,7 - 0,9 |
| RUL | Failure diperingatkan sebelum mulai (segmen 2-4) | ≥ 2 |
| RUL | Alarm RUL palsu per bulan | ≤ 1,0 |

---

## 4. Hasil Pemodelan

### 4.1 Deteksi anomali

![Perbandingan baseline dan model final](grafik/01_baseline_vs_final.png)

| Metode | Kejadian terdeteksi | Kegagalan resmi | Alarm palsu | Delay median (menit) | F1 per menit | PR-AUC | Brier |
|---|---|---|---|---|---|---|---|
| Baseline Random Forest | 12/16 | 3/4 | 3 | 8,5 | 0,984 | 0,990 | 0,003 |
| Baseline XGBoost | 12/16 | 3/4 | 7 | 7,5 | 0,973 | 0,991 | 0,002 |
| Model final terkalibrasi | 12/16 | 3/4 | 3 | 9,5 | 0,983 | 0,992 | 0,001 |
| Sistem hybrid versi awal, Merah | 14/16 | 4/4 | 5 | 10,5 | - | - | - |
| Sistem hybrid versi awal, Kuning/Merah | 16/16 | 4/4 | 59 | 8,5 | - | - | - |
| Sistem hybrid final, Merah | 14/16 | 4/4 | 4 | 11,0 | - | - | - |
| Sistem hybrid final, Kuning/Merah | 16/16 | 4/4 | 59 | 8,5 | - | - | - |

Baseline dan model final tunggal hanya mendeteksi 12 kejadian, karena April belum memiliki label sehingga tidak ada
model supervised. Sistem hybrid menutup celah ini dengan IsolationForest, sehingga F1 tetap terdeteksi.

Dibanding sistem hybrid versi awal (HGB, ambang tetap 0,5), sistem final mendeteksi kejadian yang sama
(14/16 berbanding 14/16), dengan alarm palsu 4 berbanding 5.
Model supervised final memakai 9 fitur proses yang sama dengan HGB (duty, siklus, suhu oli, arus, tekanan). Versi dengan
51 fitur menghasilkan 10 alarm palsu karena ikut mempelajari fluktuasi sensor sesaat. Catatan kejujuran: keputusan
memakai 9 fitur, baik di HGB maupun di model final, diambil setelah membandingkan hasil walk-forward yang sama, sehingga
angka alarm palsu ini sedikit optimistis dan perlu dikonfirmasi pada data sesudah Agustus 2020. Pemilihan model,
kalibrasi, dan ambang tiap bulan tetap dibuat hanya dari data latih.

Model yang terpilih tiap bulan:

| Bulan uji | Kejadian di data latih | Model terpilih | Ambang |
|---|---|---|---|
| April | 0 | - | - |
| Mei | 4 | Random Forest | 0,45 |
| Juni | 10 | XGBoost sedang | 0,90 |
| Juli | 13 | XGBoost dangkal | 0,65 |
| Agustus | 16 | Ensemble | 0,70 |

![Reliabilitas skor](grafik/02_reliabilitas.png)

Grafik reliabilitas menunjukkan skor terkalibrasi mengikuti garis diagonal: skor model sesuai dengan frekuensi kejadian
yang sebenarnya.

### 4.2 RUL

| Model | MAE semua (jam) | MAE pra-failure (jam) | MAE degradasi (jam) | MAE <= 24 jam | Skor NASA | F1 tahap | Recall Critical | Alarm RUL palsu |
|---|---|---|---|---|---|---|---|---|
| Baseline Random Forest | 8,70 | 35,10 | 44,10 | 59,93 | 358,07 | 0,33 | 0,00 | 6 |
| Baseline XGBoost | 10,26 | 33,19 | 41,40 | 56,45 | 313,05 | 0,34 | 0,00 | 6 |
| Model final | 12,11 | 34,71 | 25,38 | 28,82 | 105,31 | 0,55 | 0,75 | 0 |

Per segmen uji (model final; MAE pra-failure hanya menghitung label 0 < RUL < 72 jam):

| Segmen uji | MAE semua | MAE pra-failure | MAE degradasi tanpa override | F1 tahap | Recall Critical | Cakupan interval |
|---|---|---|---|---|---|---|
| 2 | 8,86 | 47,17 | 50,24 | 0,40 | 0,52 | 0,89 |
| 3 | 15,17 | 36,30 | 49,98 | 0,60 | 0,87 | 0,64 |
| 4 | 21,42 | 22,76 | 26,33 | 0,51 | 0,42 | 0,75 |
| 5 | 6,94 | - | - | 0,33 | - | 1,00 |

Model yang terpilih tiap segmen:

| Segmen uji | Model terpilih | Ambang alarm (jam) | Validasi |
|---|---|---|---|
| 2 | XGBoost dangkal | 6,00 | expanding-window 4 blok waktu di segmen 1 |
| 3 | XGBoost dangkal | 6,00 | expanding-window segmen 1-2 |
| 4 | XGBoost dangkal | 6,00 | expanding-window segmen 1-3 |
| 5 | XGBoost sedang | 6,00 | expanding-window segmen 1-4 |

![Prediksi RUL](grafik/03_rul_walkforward.png)

Grafik di atas memperlihatkan keterbatasan utama: sebelum F2 dan F3, prediksi tetap di sekitar 70 jam sampai kegagalan
terjadi. Skor RUL perlu dibaca pada jendela pra-failure, bukan hanya dari MAE semua baris. Karena validasi walk-forward
belum menghasilkan lead-time, tampilkan RUL sebagai perkiraan eksperimental beserta tahap dan interval, bukan sebagai
janji hitung mundur atau rekomendasi penggantian otomatis.

### 4.3 Capaian target

| Area | Metrik | Target | Hasil | Status |
|---|---|---|---|---|
| Anomali | Hybrid Merah: kejadian terdeteksi | ≥ 14 | 14,00 | Lulus |
| Anomali | Hybrid Merah: kegagalan resmi terdeteksi | ≥ 4 | 4,00 | Lulus |
| Anomali | Hybrid Merah: alarm palsu per minggu | ≤ 0,25 | 0,1830 | Lulus |
| Anomali | Model terkalibrasi: Brier skor Mei-Agu | ≤ 0,0019 | 0,0013 | Lulus |
| Anomali | Model terkalibrasi: ECE Mei-Agu | ≤ 0,05 | 0,0011 | Lulus |
| RUL | MAE sebelum failure (jam) | ≤ 12,0 | 34,71 | Tidak lulus |
| RUL | Cakupan interval 80% | 0,7 - 0,9 | 0,2353 | Tidak lulus |
| RUL | Failure diperingatkan sebelum mulai (segmen 2-4) | ≥ 2 | 0,0000 | Tidak lulus |
| RUL | Alarm RUL palsu per bulan | ≤ 1,0 | 0,0000 | Lulus |

Target yang belum tercapai:
- **Brier skor anomali** 0,0013, sedikit di atas target 0,0019.
- **MAE pra-failure RUL** 34,7 jam, di atas target 12 jam. Cakupan interval keseluruhan
  87,2% masih dalam target 70-90%, tetapi cakupan pra-failure hanya
  23,5%, sehingga intervalnya belum dapat diandalkan saat degradasi.
- **Peringatan RUL sebelum kegagalan** tidak tercapai. Bagian 8 menunjukkan bahwa sinyal 6-72 jam sebelumnya memang
  tidak ada pada F1-F3. Baseline XGBoost sempat memberi peringatan, tetapi dengan 6 alarm palsu.

---

## 5. Analisis Kesalahan (False Positive dan False Negative)

### 5.1 Matriks kebingungan per menit

Model terkalibrasi, Mei-Agustus 2020. Menit dalam margin 2 jam di sekitar kejadian tidak dihitung.

| Kondisi sebenarnya | Prediksi kejadian | Prediksi normal |
|---|---|---|
| Sebenarnya kejadian | 5.660 | 127 |
| Sebenarnya normal | 73 | 129.470 |

### 5.2 Alarm palsu (False Positive)

Daftar alarm palsu Merah, yaitu yang dikirim sebagai notifikasi ke teknisi:

| Mulai | Durasi (menit) | Kejadian terdekat | Posisi | Jarak (jam) | Duty 60 | Berbeban (menit) | Suhu oli (°C) | Kategori |
|---|---|---|---|---|---|---|---|---|
| 06 Apr 2020 15:16 | 12 | E01 | sebelum | 140,40 | 0,26 | 0,00 | 66,36 | Sesudah gap data |
| 10 May 2020 23:16 | 1 | E05 | sebelum | 62,70 | 1,00 | 29,00 | 65,33 | Beban tinggi tanpa label |
| 17 May 2020 08:35 | 9 | E06 | sebelum | 20,30 | 0,34 | 0,00 | 71,17 | Lainnya |
| 21 May 2020 18:04 | 13 | E08 | sesudah | 22,10 | 0,38 | 15,00 | 72,99 | Lainnya |

![Kategori alarm palsu](grafik/04_fp_kategori.png)

Temuan:
1. Semua alarm palsu Merah berdurasi pendek (1-71 menit).
2. 0 dari 4 terjadi kurang dari 6 jam dari kejadian berlabel. Pola sensornya mirip kejadian di dekatnya,
   sehingga kemungkinan besar mesin belum pulih sepenuhnya atau label kejadian terlalu sempit.
3. 1 alarm muncul sesaat setelah data sensor kembali dari gap, saat fitur rata-rata bergerak belum stabil.
4. Alarm Kuning palsu lebih banyak (59 episode, 2,7 per minggu). Kuning hanya tampil di dashboard,
   tidak dikirim sebagai notifikasi.

### 5.3 Kejadian terlewat (False Negative)

| Kejadian | Kegagalan resmi | Durasi (menit) | Merah | Kuning/Merah | Delay Merah (menit) | Keterangan |
|---|---|---|---|---|---|---|
| E01 | Tidak | 700 | Ya | Ya | 72 | - |
| E02_F1 | Ya | 1.530 | Ya | Ya | 91 | - |
| E03 | Tidak | 40 | Tidak | Ya | - | April: model supervised belum ada, dan kejadian < 60 menit sehingga aturan cold start (IF 60 menit) tidak sempat menjadi Merah |
| E04 | Tidak | 20 | Tidak | Ya | - | April: model supervised belum ada, dan kejadian < 60 menit sehingga aturan cold start (IF 60 menit) tidak sempat menjadi Merah |
| E05 | Tidak | 599 | Ya | Ya | 2 | - |
| E06 | Tidak | 30 | Ya | Ya | 8 | - |
| E07 | Tidak | 50 | Ya | Ya | 10 | - |
| E08 | Tidak | 1.310 | Ya | Ya | 26 | - |
| E09 | Tidak | 20 | Ya | Ya | 6 | - |
| E10_F2 | Ya | 390 | Ya | Ya | -1 | - |
| E11 | Tidak | 40 | Ya | Ya | 12 | - |
| E12 | Tidak | 60 | Ya | Ya | 27 | - |
| E13_F3 | Ya | 3.150 | Ya | Ya | 9 | - |
| E14 | Tidak | 90 | Ya | Ya | 28 | - |
| E15_F4 | Ya | 270 | Ya | Ya | -9 | - |
| E16 | Tidak | 60 | Ya | Ya | 23 | - |

Temuan:
1. Kejadian yang tidak mencapai Merah: E03, E04. Keduanya kejadian singkat di April, saat model
   supervised belum tersedia. Keduanya tetap muncul sebagai Kuning.
2. Semua kejadian Mei-Agustus dan keempat kegagalan resmi mencapai Merah.
3. F4 sudah berstatus Merah 9 menit sebelum label kegagalan dimulai, sejalan dengan pola degradasi bertahap F4.
4. Delay median sekitar 11 menit menunjukkan sistem ini bekerja sebagai **deteksi dini**, bukan peramalan
   berhari-hari sebelumnya.

---

## 6. Analisis Bisnis: Simulasi ROI

### 6.1 Asumsi

Perhitungan memakai **1 UB = biaya satu perbaikan terencana** sesuai definisi dokumen. Biaya dasar dan batas rendah/tinggi
berikut mengikuti tabel asumsi biaya yang disepakati:

| Parameter | Batas rendah | Dasar | Batas tinggi | Dasar dalam rupiah |
|---|---|---|---|---|
| Kegagalan besar per unit per tahun | 6,86 | 6,86 | 6,86 | - |
| Downtime per kegagalan (jam) | 21,87 | 21,87 | 21,87 | - |
| Biaya downtime per jam (UB/jam) | 0,20 UB | 0,50 UB | 1,50 UB | Rp 25 juta/jam |
| Biaya perbaikan darurat (UB) | 2,00 UB | 3,00 UB | 5,00 UB | Rp 150 juta |
| Biaya perbaikan terencana prediktif (UB) | 0,80 UB | 1,00 UB | 1,50 UB | Rp 50 juta |
| Biaya inspeksi per alarm palsu (UB) | 0,05 UB | 0,10 UB | 0,20 UB | Rp 5 juta |
| Interval penggantian terjadwal (bulan) | 12 | 6 | 3 | - |
| Biaya penggantian terjadwal (UB/penggantian) | 1,00 UB | 1,20 UB | 2,00 UB | Rp 60 juta |
| Kegagalan yang lolos di preventif | 10% | 30% | 60% | - |
| Biaya sistem prediktif (UB/tahun) | 0,50 UB | 1,00 UB | 3,00 UB | Rp 50 juta/tahun |

Dokumen tidak menetapkan frekuensi kegagalan dan durasi downtime. Untuk ilustrasi, frekuensi dasar diambil dari 4
kegagalan resmi selama 7 bulan pada satu unit (6,86 kegagalan/tahun).
Durasi downtime diproksikan dengan rata-rata lama interval label 4 kegagalan (21,87 jam),
bukan catatan downtime operasional terverifikasi. Ganti kedua nilai ini dengan data operasional bila tersedia.

**Konversi ke rupiah (ilustrasi).** Satu UB diasumsikan setara **Rp 50 juta**. Acuannya, harga satu unit
kompresor udara kereta berada di kisaran €8.500-11.000 per unit (sekitar Rp 150-210 juta) [4]. Perbaikan terencana
(ganti katup, seal, filter, atau bearing ditambah tenaga teknisi) diperkirakan sekitar sepertiga harga unit, sehingga
1 UB ≈ Rp 50 juta, dan perbaikan darurat (3 UB ≈ Rp 150 juta) kurang lebih setara penggantian
unit. Porsi sepertiga adalah asumsi tim, dan sumber harga unit tidak menyebut tahun maupun status unit (baru atau
rekondisi). Sebagai pembanding skala, kontrak suku cadang KAI Commuter bernilai Rp 734 miliar untuk tiga tahun [5].
Nilai rupiah hanya memberi gambaran nominal: rumus dan tabel asumsi tetap dalam UB, dan persentase ROI tidak berubah
berapa pun nilai rupiah per UB.

**Biaya downtime.** Biaya downtime (0,5 UB/jam ≈ Rp 25 juta/jam pada nilai dasar) mencakup kehilangan pendapatan selama
rangkaian tidak beroperasi, biaya operasional yang tetap berjalan (kru, energi, rangkaian pengganti), serta biaya
gangguan layanan seperti pengalihan perjalanan atau kompensasi penumpang [6]. Biaya perbaikan tidak termasuk di sini
karena sudah dihitung terpisah sebagai perbaikan darurat. Nilai per jam adalah asumsi karena data biaya downtime
rangkaian kereta tidak tersedia untuk publik; sensitivitasnya diuji pada rentang 0,2-1,5 UB/jam (bagian 7).

Metrik deteksi diambil dari validasi walk-forward sistem hybrid final, bukan LOFO: recall kegagalan resmi 100%
dan 0,78 episode alarm Merah palsu per minggu per unit. Walk-forward dipakai
untuk menghindari pelatihan dengan data masa depan; ini merupakan perbedaan metode dari LOFO yang disebut dokumen.
Kejadian kecil yang tidak cocok dengan kegagalan resmi dihitung konservatif sebagai FP.

Perhitungan per tahun mengikuti rumus ruang lingkup:
- Reaktif = N kegagalan × (jam downtime × biaya downtime/jam + perbaikan darurat).
- Preventif = jumlah penggantian terjadwal × biaya penggantian per penggantian + biaya kegagalan yang lolos.
- Prediktif = TP × perbaikan terencana + FN × biaya kegagalan reaktif + FP × inspeksi + biaya operasi sistem.
- TP/FN dihitung dari frekuensi kegagalan tahunan × recall; FP dari episode alarm Merah tanpa kegagalan resmi yang cocok
  (alarm pada masa maintenance dikecualikan), dianualisasi per unit.
- Penghematan prediktif terhadap strategi = biaya strategi pembanding − biaya prediktif.
- ROI tahunan terhadap tiap pembanding = penghematan tahunan ÷ biaya sistem tahunan × 100%.
- Tidak ditampilkan NPV, balik modal, atau capex: rumus tersebut tidak termasuk dalam asumsi ROI pada dokumen.

### 6.2 Hasil

| Skenario | TP/tahun | FN/tahun | FP/tahun | Biaya reaktif/tahun (UB) | Biaya preventif/tahun (UB) | Biaya prediktif/tahun (UB) | Penghematan vs reaktif/tahun (UB) | ROI vs reaktif | Penghematan vs preventif/tahun (UB) | ROI vs preventif |
|---|---|---|---|---|---|---|---|---|---|---|
| Batas rendah | 6,9 | 0,0 | 40,4 | 43,71 UB | 5,37 UB | 8,01 UB | 35,70 UB | 7.140,1% | -2,64 UB | -527,4% |
| Dasar | 6,9 | 0,0 | 40,4 | 95,56 UB | 31,07 UB | 11,90 UB | 83,66 UB | 8.365,6% | 19,17 UB | 1.916,6% |
| Batas tinggi | 6,9 | 0,0 | 40,4 | 259,24 UB | 163,55 UB | 21,37 UB | 237,87 UB | 7.928,9% | 142,17 UB | 4.739,0% |

Dalam rupiah (1 UB = Rp 50 juta, per unit APU per tahun):

| Skenario | Reaktif/tahun | Preventif/tahun | Prediktif/tahun | Hemat vs reaktif/tahun | Hemat vs preventif/tahun |
|---|---|---|---|---|---|
| Batas rendah | Rp 2,19 miliar | Rp 269 juta | Rp 400 juta | Rp 1,79 miliar | -Rp 132 juta |
| Dasar | Rp 4,78 miliar | Rp 1,55 miliar | Rp 595 juta | Rp 4,18 miliar | Rp 958 juta |
| Batas tinggi | Rp 12,96 miliar | Rp 8,18 miliar | Rp 1,07 miliar | Rp 11,89 miliar | Rp 7,11 miliar |

![Simulasi ROI](grafik/05_roi_skenario.png)

---

## 7. Analisis Sensitivitas

### 7.1 Sensitivitas parameter

Setiap parameter pada nilai dasar digeser ±30%, parameter lain tetap. ROI sensitivitas mengacu pada pembanding reaktif:

![Tornado sensitivitas](grafik/06_tornado_sensitivitas.png)

| Parameter | ROI jika -30% (%) | ROI jika +30% (%) | Rentang (poin %) |
|---|---|---|---|
| Biaya sistem prediktif (UB/tahun) | 11.993,7 | 6.412,0 | 5.581,7 |
| Kegagalan besar per unit per tahun | 5.704,6 | 11.026,6 | 5.322,0 |
| Downtime per kegagalan (jam) | 6.116,0 | 10.615,1 | 4.499,1 |
| Biaya downtime per jam (UB/jam) | 6.116,0 | 10.615,1 | 4.499,1 |
| Recall kegagalan resmi | 5.704,6 | 8.365,6 | 2.661,0 |
| Biaya perbaikan darurat (UB) | 7.748,4 | 8.982,7 | 1.234,3 |
| Biaya perbaikan terencana prediktif (UB) | 8.571,3 | 8.159,8 | 411,4 |
| Biaya inspeksi per alarm palsu (UB) | 8.486,9 | 8.244,2 | 242,7 |
| Alarm Merah tanpa kegagalan resmi per minggu | 8.486,9 | 8.244,2 | 242,7 |

### 7.2 Titik impas

Nilai parameter yang membuat ROI terhadap reaktif tepat nol, parameter lain tetap pada nilai dasar:

| Parameter | Nilai dasar | Titik impas | Syarat ROI positif |
|---|---|---|---|
| Recall kegagalan resmi | 1,00 | 0,06 | minimal |
| Alarm Merah tanpa kegagalan resmi per minggu | 0,78 | 16,86 | maksimal |
| Kegagalan besar per unit per tahun | 6,86 | 0,39 | minimal |

### 7.3 Sensitivitas ambang

![Sensitivitas ambang](grafik/07_sensitivitas_ambang.png)

| Ambang | Kejadian Mei-Agu (dari 12) | Alarm palsu | Delay median (menit) | Penghematan vs reaktif/tahun (dasar, UB) |
|---|---|---|---|---|
| 0,10 | 12 | 7 | 6,50 | 82,34 UB |
| 0,15 | 12 | 5 | 7,00 | 82,94 UB |
| 0,20 | 12 | 3 | 7,00 | 83,53 UB |
| 0,25 | 12 | 3 | 7,00 | 83,53 UB |
| 0,30 | 12 | 3 | 7,00 | 83,53 UB |
| 0,35 | 12 | 3 | 7,00 | 83,53 UB |
| 0,40 | 12 | 3 | 7,00 | 83,53 UB |
| 0,45 | 12 | 3 | 7,00 | 83,53 UB |
| 0,50 | 12 | 0 | 15,50 | 84,43 UB |
| 0,55 | 12 | 0 | 15,50 | 84,43 UB |
| 0,60 | 12 | 0 | 15,50 | 84,43 UB |
| 0,65 | 12 | 0 | 15,50 | 84,43 UB |
| 0,70 | 12 | 0 | 15,50 | 84,13 UB |
| 0,75 | 12 | 0 | 15,50 | 84,13 UB |
| 0,80 | 12 | 0 | 15,50 | 84,13 UB |
| 0,85 | 12 | 0 | 15,50 | 84,13 UB |
| 0,90 | 12 | 0 | 15,50 | 84,13 UB |
| 0,95 | 9 | 0 | 21,00 | 85,32 UB |

Kurva ini dihitung pada data uji, sehingga hanya menggambarkan trade-off dan tidak dipakai untuk memilih ambang.

### 7.4 Interpretasi

1. ROI paling dipengaruhi oleh **biaya sistem prediktif (ub/tahun)**, **kegagalan besar per unit per tahun**, dan
   **downtime per kegagalan (jam)**. Ketiganya asumsi bisnis, sehingga validasi data biaya lebih mendesak
   daripada peningkatan model.
2. Pada nilai dasar, ROI terhadap reaktif tetap positif selama alarm Merah tanpa kegagalan resmi di bawah 16,86 per minggu per unit
   (saat ini 0,78).
3. Pada data uji, ambang 0,50-0,90 memberi alarm palsu paling sedikit tanpa kehilangan kejadian. Ambang yang
   dipilih validasi dalam berada di kisaran 0,45-0,90. Kurva ini dihitung pada data uji, jadi tidak dipakai untuk
   memilih ambang.
4. Karena recall kegagalan resmi sudah 100% pada sampel kecil ini, model belum membuktikan lead-time yang memberi
   penghematan. ROI tetap simulasi bersyarat, bukan bukti kelayakan investasi.

---

## 8. Pola Degradasi dan Insight

### 8.1 Perilaku sensor menjelang kegagalan

![Lintasan sensor](grafik/08_lintasan_degradasi.png)

Rata-rata sensor per jendela waktu sebelum kegagalan. Sebagai acuan, persentil 95 kondisi sehat (Agustus): duty 60
menit 0,19, lama berbeban 1 menit, suhu oli 69,4 °C.

| Kegagalan | Waktu sebelum kegagalan | Duty 60 | Berbeban (menit) | Suhu oli (°C) | Arus motor (A) | Jumlah menit |
|---|---|---|---|---|---|---|
| F1 | Failure | 1,00 | 709,00 | 74,39 | 5,66 | 1.417 |
| F1 | 12-24 j | 0,08 | 0,09 | 52,52 | 1,38 | 358 |
| F1 | 24-48 j | 0,09 | 0,13 | 57,25 | 1,46 | 1.334 |
| F1 | 48-72 j | 0,08 | 0,07 | 56,52 | 1,40 | 1.397 |
| F2 | Failure | 0,96 | 205,83 | 75,81 | 5,40 | 391 |
| F2 | 0-2 j | 0,13 | 1,11 | 63,27 | 1,77 | 120 |
| F2 | 2-6 j | 0,11 | 0,10 | 64,55 | 1,82 | 240 |
| F2 | 6-12 j | 0,13 | 0,10 | 67,33 | 2,09 | 360 |
| F2 | 12-24 j | 0,15 | 0,15 | 66,90 | 2,37 | 526 |
| F2 | 24-48 j | 0,14 | 0,14 | 67,66 | 2,34 | 1.207 |
| F3 | Failure | 0,99 | 678,02 | 75,47 | 5,47 | 2.872 |
| F3 | 0-2 j | 0,12 | 0,62 | 64,33 | 1,88 | 120 |
| F3 | 2-6 j | 0,12 | 0,10 | 63,90 | 1,92 | 240 |
| F3 | 6-12 j | 0,10 | 0,10 | 61,99 | 1,57 | 360 |
| F3 | 12-24 j | 0,11 | 0,08 | 64,61 | 1,78 | 720 |
| F3 | 24-48 j | 0,15 | 1,58 | 64,67 | 1,96 | 1.322 |
| F3 | 48-72 j | 0,14 | 1,77 | 63,50 | 1,78 | 864 |
| F4 | Failure | 0,97 | 131,99 | 83,94 | 5,53 | 271 |
| F4 | 0-2 j | 0,58 | 1,79 | 77,37 | 4,91 | 120 |
| F4 | 2-6 j | 0,42 | 0,58 | 73,89 | 4,58 | 240 |
| F4 | 6-12 j | 0,38 | 0,42 | 72,52 | 4,50 | 360 |
| F4 | 12-24 j | 0,27 | 0,31 | 70,15 | 3,68 | 302 |
| F4 | 24-48 j | 0,16 | 1,60 | 65,64 | 1,82 | 995 |
| F4 | 48-72 j | 0,19 | 0,17 | 70,01 | 2,96 | 1.020 |

Temuan:
1. **F1, F2, dan F3 terjadi mendadak.** Pada jam terakhir yang memiliki data sebelum kegagalan, duty kompresor masih
   sekitar 0,1, di bawah batas sehat. Saat gagal, kompresor bekerja terus-menerus (duty mendekati 1) tetapi tidak pernah
   mencapai tekanan target. Ini pola khas kebocoran udara.
2. **F4 menunjukkan degradasi bertahap.** Duty naik dari 0,16 (24-48 jam sebelumnya) menjadi 0,27 (12-24 jam),
   0,42 (2-6 jam), dan 0,58 (0-2 jam). Arus motor juga naik bersamaan. Pola seperti ini dapat
   dipantau dengan aturan sederhana seperti "duty 6 jam di atas 0,3".
3. **Suhu oli naik sebagai akibat**, setelah kompresor bekerja lama, sehingga lebih cocok untuk konfirmasi daripada
   peringatan dini.

### 8.2 Kejadian kecil sebagai prekursor

| Kegagalan | Kejadian kecil 14 hari sebelumnya | Jarak terdekat (hari) |
|---|---|---|
| F1 (18 Apr) | E01 | 5,0 |
| F2 (29 May) | E06, E07, E08, E09 | 6,6 |
| F3 (05 Jun) | E09, E11, E12 | 2,0 |
| F4 (15 Jul) | E14 | 6,8 |

Semua kegagalan resmi didahului kejadian kecil dalam 14 hari sebelumnya, dengan jarak terdekat
2-7 hari. Sebaliknya, 5 dari 12 kejadian kecil diikuti kegagalan resmi dalam 7 hari.
Kejadian kecil yang sudah pulih sebaiknya tidak diabaikan, tetapi dijadikan pemicu inspeksi dalam seminggu.

### 8.3 Fitur yang paling berpengaruh

![Fitur terpenting](grafik/09_fitur_penting.png)

Model anomali:

| Fitur | Model anomali | Model RUL |
|---|---|---|
| duty_15 | 0,578 | 0,001 |
| load_run_min | 0,236 | 0,009 |
| tp2_mean_60 | 0,092 | 0,002 |
| duty_60 | 0,035 | 0,007 |
| h1_mean_60 | 0,032 | 0,015 |
| curr_mean_60 | 0,009 | 0,102 |
| cycles_60 | 0,008 | 0,001 |
| oil_mean_15 | 0,008 | 0,353 |

Model RUL:

| Fitur | Model anomali | Model RUL |
|---|---|---|
| oil_mean_15 | 0,008 | 0,353 |
| discharge_slope_60 | - | 0,116 |
| curr_mean_60 | 0,009 | 0,102 |
| cooling_deficit | - | 0,034 |
| oil_mean_60 | - | 0,034 |
| tp3_min_360 | - | 0,030 |
| discharge_slope_15 | - | 0,028 |
| duty_1440 | - | 0,027 |

- Model anomali terutama memakai duty_15, load_run_min, tp2_mean_60, duty_60: tekanan, laju pengisian tekanan, dan lama kompresor
  berbeban. Saat terjadi kebocoran, tekanan turun dan kompresor butuh waktu lebih lama untuk mengisi.
- Model RUL terutama memakai oil_mean_15, discharge_slope_60, curr_mean_60. Suhu oli dipengaruhi suhu lingkungan dan musim, sehingga model RUL
  perlu dilatih ulang secara berkala.

---

## 9. Kesimpulan dan Rekomendasi

### 9.1 Kesimpulan

1. Sistem hybrid final mendeteksi 14/16 kejadian dan semua kegagalan resmi, dengan skor yang terkalibrasi.
2. RUL belum menunjukkan lead-time pada walk-forward dan belum layak dipakai sendiri untuk menjadwalkan penggantian.
3. ROI tiga strategi hanya simulasi berbasis asumsi, dan sensitivitasnya bergantung pada frekuensi kegagalan serta
   biaya komponen, downtime, inspeksi, dan sistem.
4. Kejadian kecil adalah tanda peringatan terkuat menjelang kegagalan besar.

### 9.2 Rekomendasi

1. Gunakan sistem hybrid final untuk notifikasi Merah, dan tampilkan RUL sebagai tahap beserta intervalnya.
2. Tinjau ulang batas label bersama teknisi, terutama di sekitar E14 dan E16, untuk mengurangi alarm palsu.
3. Kumpulkan data biaya nyata (biaya per kegagalan, durasi gangguan, biaya inspeksi) untuk memperbarui analisis ROI.
4. Lakukan inspeksi dalam 7 hari setelah setiap kejadian kecil.
5. Latih ulang model setiap bulan. Model RUL membutuhkan lebih banyak data kegagalan (idealnya 10 atau lebih).

---

## 10. Keterbatasan

1. Hanya satu unit APU dengan 4 kegagalan resmi dan 16 kejadian, sehingga hasil perlu divalidasi pada data lain.
2. Target metrik ditetapkan oleh tim setelah melihat baseline.
3. Seluruh analisis biaya berbasis asumsi.
4. Kinerja model final yang diekspor (dilatih dengan seluruh data) belum dapat diukur langsung, sehingga diwakili oleh
   hasil walk-forward.

---

## Daftar Pustaka

- [1] Davari, N., Veloso, B., Ribeiro, R. P., Pereira, P. M., & Gama, J. (2021). Predictive maintenance based on anomaly
  detection using deep learning for air production unit in the railway industry. *IEEE DSAA 2021*.
- [2] Veloso, B., Ribeiro, R. P., Gama, J., & Pereira, P. M. (2022). The MetroPT dataset for predictive maintenance.
  *Scientific Data*, 9, 764.
- [3] Saxena, A., Goebel, K., Simon, D., & Eklund, N. (2008). Damage propagation modeling for aircraft engine run-to-failure
  simulation. *PHM 2008*.

Sumber asumsi biaya (bagian 6.1):

- [4] Daftar harga komponen kompresor tipe Knorr-Bremse (spreadsheet publik, tanpa tahun).
  https://docs.google.com/spreadsheets/d/1B2FjPw758KyklRspP4W3rqZNrt0mtDM3/edit
- [5] PwC Indonesia (2024). KCI, JRTM cooperate to procure Commuter Line spare parts for Rp734 billion.
  https://pwc.com/id/en/media-centre/infrastructure-news/march-2024/kci-jrtm-cooperate-to-procure-commuter-line-spare-parts-for-rp73.html
- [6] Kementerian Perhubungan (2019). Peraturan Menteri Perhubungan No. PM 63 Tahun 2019 tentang Standar Pelayanan
  Minimal Angkutan Orang dengan Kereta Api (kompensasi keterlambatan; berlaku untuk KA antarkota).
- Bisnis.com (2023). KAI Commuter mulai retrofit 19 trainset KRL, biayanya sentuh Rp2,2 triliun.
  https://ekonomi.bisnis.com/read/20231104/98/1711058/kai-commuter-mulai-retrofit-19-trainset-krl-biayanya-sentuh-rp22-triliun
- Magazine Industry USA. Replacement of compressed air production units on TGV PSE trains (interval perawatan kompresor).
  https://magazine-industry-usa.com/news/1108-replacement-of-compressed-air-production-units-on-tgv-pse-trains

## Lampiran: Berkas Proyek

| Berkas | Isi |
|---|---|
| `train_baseline.py` | Pelatihan dan evaluasi model baseline |
| `train_final_calibrated.py` | Pelatihan model final, kalibrasi, optimasi ambang, ekspor model |
| `analysis_report.py` | Analisis dan pembuatan laporan ini |
| `predict.py` | Pemakaian model final pada data baru |
| `output/model/final/` | Model final dan metadata |
| `output/model/prediksi_walkforward.parquet` | Prediksi per menit April-Agustus 2020 |
