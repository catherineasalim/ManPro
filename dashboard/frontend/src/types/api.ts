export type Status = "Hijau" | "Kuning" | "Merah" | "Abu-abu";

export interface ReplayMetadata {
  start: string;
  end: string;
  rows: number;
  interval: string;
  signals: string[];
  statuses: Status[];
  model_summary: ModelSummary | null;
}

export interface MonthlyThreshold {
  month: string;
  threshold: number | null;
  supervised_active: boolean;
}

export interface ModelSummary {
  anomaly_model: string | null;
  anomaly_members: string[];
  anomaly_calibration: string | null;
  anomaly_threshold: number | null;
  anomaly_features: string[];
  hybrid_events_detected: string | null;
  hybrid_official_detected: string | null;
  hybrid_false_alarm_episodes: number | null;
  hybrid_false_alarms_per_week: number | null;
  calibrated_ece: number | null;
  rul_model: string | null;
  rul_mae_pre_failure_hours: number | null;
  rul_critical_recall: number | null;
  targets_passed: number | null;
  targets_total: number | null;
  monthly_thresholds: MonthlyThreshold[];
}

export interface Frame {
  timestamp: string;
  status: Status;
  trigger: string | null;
  probability: number | null;
  threshold: number | null;
  rul_hours: number | null;
  rul_lower: number | null;
  rul_upper: number | null;
  rul_stage: string | null;
  model_active: boolean | null;
  sensors: Record<string, number | boolean | null>;
}

export interface TelemetryPoint {
  timestamp: string;
  values: Record<string, number | boolean | null>;
  status: Status;
  probability: number | null;
  threshold: number | null;
  rul_hours: number | null;
  rul_lower: number | null;
  rul_upper: number | null;
  rul_stage: string | null;
}

export interface TelemetryResponse {
  points: TelemetryPoint[];
  total_points: number;
  downsampled: boolean;
}

export interface AlarmRecord {
  id: string;
  started_at: string;
  ended_at: string;
  duration_minutes: number;
  highest_status: Status;
  red_started_at: string | null;
  trigger: string | null;
  sensors: Record<string, number | boolean | null>;
}

export interface NotificationRecord {
  id: string;
  timestamp: string;
  status: Status;
  channel: "Email" | "WhatsApp Bot";
  title: string;
  message: string;
  delivery: "Simulasi" | "Belum dikirim" | "Belum dikonfigurasi" | "Mengirim" | "Terkirim" | "Gagal";
  delivery_error: string | null;
}

export interface ROICosts {
  kegagalan_per_unit_tahun: number;
  downtime_jam_per_kegagalan: number;
  biaya_downtime_per_jam: number;
  biaya_perbaikan_darurat: number;
  biaya_perbaikan_terencana: number;
  biaya_inspeksi: number;
  interval_penggantian_bulan: number;
  biaya_penggantian_preventif: number;
  kegagalan_lolos_preventif: number;
  biaya_sistem: number;
}

export interface ROIRequest {
  scenario: "Batas rendah" | "Dasar" | "Batas tinggi";
  costs?: Partial<ROICosts>;
}

export interface ROIScenario {
  name: string;
  costs: ROICosts;
  annual_costs: Record<"Reaktif" | "Preventif" | "Prediktif", number>;
  savings_vs_reactive: number;
  savings_vs_preventive: number;
  roi_vs_reactive_percent: number;
  roi_vs_preventive_percent: number;
}

export interface ROIResponse {
  detection_basis: { official_recall: number; false_red_alarms_per_week: number };
  rupiah_per_ub: number;
  selected: ROIScenario;
  scenarios: ROIScenario[];
  sensitivity: { parameter: string; nilai: number; roi_minus_30: number; roi_plus_30: number; rentang: number }[];
  break_even: { parameter: string; nilai_sekarang: number; titik_impas: number | null }[];
  per_failure_costs: Record<"Reaktif" | "Preventif" | "Prediktif", number | null>;
}
