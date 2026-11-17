"""
Jalankan semua tahap berurutan.

Jalankan dari root repo:  python -m anomaly_detection.run_all
Pilihan:
  --dengan-preprocessing   buat ulang output/dataprep/ dari CSV mentah (butuh MetroPT3(AirCompressor).csv di root repo)
  --tanpa-hybrid           lewati train_hybrid dan visualize_hybrid (pakai output/hybrid/ yang sudah ada)

Urutan: tes, (preprocessing), hybrid, grafik hybrid, baseline, model final, laporan, uji model final.
Berhenti di tahap pertama yang gagal.
"""
import argparse
import subprocess
import sys
import time

TESTS = ["anomaly_detection.tests.test_hybrid", "anomaly_detection.tests.test_model"]
PREPROCESSING = ["anomaly_detection.preprocessing.preprocess_dataprep"]
HYBRID = ["anomaly_detection.anomali.train_hybrid", "anomaly_detection.anomali.visualize_hybrid"]
MODEL = [
    "anomaly_detection.rul_final.train_baseline",
    "anomaly_detection.rul_final.train_final_calibrated",
    "anomaly_detection.laporan.analysis_report",
    "anomaly_detection.rul_final.predict",
]


def main():
    parser = argparse.ArgumentParser(description="Jalankan semua tahap berurutan")
    parser.add_argument("--dengan-preprocessing", action="store_true")
    parser.add_argument("--tanpa-hybrid", action="store_true")
    args = parser.parse_args()

    steps = TESTS + (PREPROCESSING if args.dengan_preprocessing else []) + ([] if args.tanpa_hybrid else HYBRID) + MODEL
    start = time.time()
    for i, module in enumerate(steps, 1):
        print(f"\n[{i}/{len(steps)}] python -m {module}", flush=True)
        t0 = time.time()
        if subprocess.run([sys.executable, "-m", module]).returncode != 0:
            sys.exit(f"\nGAGAL di {module}. Tahap berikutnya tidak dijalankan.")
        print(f"[{i}/{len(steps)}] selesai dalam {time.time() - t0:.0f} detik", flush=True)
    print(f"\nSemua {len(steps)} tahap selesai dalam {(time.time() - start) / 60:.1f} menit.")


if __name__ == "__main__":
    main()
