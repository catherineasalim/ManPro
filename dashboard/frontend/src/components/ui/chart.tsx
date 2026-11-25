import type { ReactNode } from "react";
import { ResponsiveContainer, Tooltip } from "recharts";
import { cn } from "../../lib/utils";

export function ChartContainer({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("chart-container", className)}><ResponsiveContainer width="100%" height="100%">{children as never}</ResponsiveContainer></div>;
}

export function ChartTooltip({ formatter, labelFormatter }: {
  formatter?: (value: number, name: string) => [string, string];
  labelFormatter?: (label: string) => string;
}) {
  return <Tooltip contentStyle={{ background: "#18211f", border: "1px solid #2b3a35", borderRadius: 12, color: "#eef3f0", fontSize: 13 }} itemStyle={{ color: "#dce5df" }} labelStyle={{ color: "#95a79d", marginBottom: 6 }} formatter={formatter} labelFormatter={labelFormatter} />;
}
