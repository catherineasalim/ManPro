import { Brush, CartesianGrid, Line, LineChart, ReferenceLine, Tooltip as RechartsTooltip, XAxis, YAxis } from "recharts";
import { ChartContainer } from "../ui/chart";
import type { TelemetryPoint } from "../../types/api";
import { formatNumber } from "../../lib/utils";

const palette: Record<string, string> = { TP2: "#f6b64b", TP3: "#3dd6b5", Oil_temperature: "#f17967", Motor_current: "#8d9bff", p_terkalibrasi: "#bf9bff", rul_hours: "#3dd6b5" };
const names: Record<string, string> = { TP2: "TP2", TP3: "TP3", Oil_temperature: "Suhu oli", Motor_current: "Arus motor", p_terkalibrasi: "Skor anomali", rul_hours: "RUL" };
const units: Record<string, string> = { TP2: "bar", TP3: "bar", Oil_temperature: "°C", Motor_current: "A", rul_hours: "jam" };

export function TelemetryChart({ data, signals, cursor, percent = false, unit = "" }: { data: TelemetryPoint[]; signals: string[]; cursor?: string | null; percent?: boolean; unit?: string }) {
  const chartData = data.map((point) => ({ timestamp: point.timestamp, ...point.values, probability: point.probability, threshold: point.threshold, rul_hours: point.rul_hours }));
  const activeColor = signals[0] ? palette[signals[0]] : "#3dd6b5";
  return <ChartContainer className="telemetry-chart">
    <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 6, left: -15 }}>
      <CartesianGrid stroke="#26332f" strokeDasharray="3 5" vertical={false} />
      <XAxis dataKey="timestamp" tickFormatter={(value: string) => new Date(value).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })} tick={{ fill: "#73857d", fontSize: 10 }} axisLine={{ stroke: "#34413c" }} tickLine={false} minTickGap={45} />
      <YAxis tick={{ fill: "#73857d", fontSize: 10 }} axisLine={false} tickLine={false} width={54} domain={percent ? [0, 1] : ["auto", "auto"]} tickFormatter={(value: number) => percent ? `${Math.round(value * 100)}%` : formatNumber(value, 0)} />
      <RechartsTooltip contentStyle={{ background: "#18211f", border: "1px solid #2b3a35", borderRadius: 12, fontSize: 12 }} labelFormatter={(label) => new Date(String(label)).toLocaleString("id-ID")} formatter={(value, name) => [percent ? `${formatNumber(Number(value) * 100, 1)}%` : `${formatNumber(Number(value), 2)} ${units[String(name)] ?? unit}`.trim(), names[String(name)] ?? (String(name) === "threshold" ? "Ambang model" : String(name))]} />
      {cursor && <ReferenceLine x={cursor} stroke="#f6b64b" strokeDasharray="4 4" />}
      {signals.map((signal) => <Line key={signal} type="monotone" dataKey={signal === "p_terkalibrasi" ? "probability" : signal} name={signal === "p_terkalibrasi" ? signal : signal} stroke={palette[signal] ?? activeColor} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />)}
      {signals.includes("p_terkalibrasi") && <Line type="monotone" dataKey="threshold" name="Ambang model" stroke="#f6b64b" strokeWidth={1.3} strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} />}
      {chartData.length > 120 && <Brush dataKey="timestamp" height={19} stroke="#41534b" fill="#15201c" travellerWidth={8} tickFormatter={() => ""} />}
    </LineChart>
  </ChartContainer>;
}
