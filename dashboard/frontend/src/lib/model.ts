export const COLD_START_TEXT = "Model supervised belum aktif (cold start): status berasal dari Isolation Forest";

/** Teks perbandingan skor dengan ambang. Skor 0 di April bukan hasil model, jadi jangan dibandingkan. */
export function anomalyLevel(
  probability: number | null | undefined,
  threshold: number | null | undefined,
  modelActive: boolean | null | undefined,
) {
  if (probability == null) return "Belum tersedia";
  if (modelActive === false) return COLD_START_TEXT;
  if (threshold == null) return "Ambang tidak tersedia";
  // Aturan status memakai skor > ambang (anomaly_detection/common/hybrid.py), bukan >=.
  return probability > threshold ? "Ambang model terlampaui" : "Di bawah ambang";
}
