import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchHistory, type HistoryRange, type Metal } from "../api";
import { formatINR, formatShortDate } from "../format";
import type { PriceMode } from "./PriceCard";

const RANGES: HistoryRange[] = ["1w", "1m", "3m", "6m", "1y"];

export default function HistoryChart({ mode }: { mode: PriceMode }) {
  const [metal, setMetal] = useState<Metal>("gold");
  const [range, setRange] = useState<HistoryRange>("1m");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["history", metal, range],
    queryFn: () => fetchHistory(metal, range),
  });

  const points = data?.points ?? [];

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Price history</h2>
        <div className="controls">
          <div className="seg">
            {(["gold", "silver"] as Metal[]).map((m) => (
              <button key={m} className={m === metal ? "on" : ""} onClick={() => setMetal(m)}>
                {m === "gold" ? "Gold" : "Silver"}
              </button>
            ))}
          </div>
          <div className="seg">
            {RANGES.map((r) => (
              <button key={r} className={r === range ? "on" : ""} onClick={() => setRange(r)}>
                {r.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading && <p className="muted">Loading chart…</p>}
      {isError && <p className="muted">Couldn't load history.</p>}

      {!isLoading && !isError && points.length < 2 && (
        <p className="muted">
          Not enough data for a chart yet. History builds up as the backend saves a price each day.
          {points.length === 1 && " So far there is 1 day of data."}
        </p>
      )}

      {points.length >= 2 && (
        <div className="chart">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis
                dataKey="date"
                tickFormatter={formatShortDate}
                stroke="var(--muted)"
                fontSize={12}
                minTickGap={24}
              />
              <YAxis
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => formatINR(v)}
                stroke="var(--muted)"
                fontSize={12}
                width={80}
              />
              <Tooltip
                formatter={(v: number) => [
                  formatINR(v) + " / g",
                  mode === "retail" ? "Retail price" : "Spot price",
                ]}
                labelFormatter={(l: string) => formatShortDate(l)}
                contentStyle={{
                  background: "var(--card)",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                }}
              />
              <Line
                type="monotone"
                dataKey={mode === "retail" ? "retail_per_gram" : "spot_per_gram"}
                stroke={metal === "gold" ? "var(--gold)" : "var(--silver)"}
                strokeWidth={2.5}
                dot={points.length < 20}
              />
            </LineChart>
          </ResponsiveContainer>
          <p className="muted small">
            {mode === "retail"
              ? "Indicative retail price per gram: spot plus import duty and GST, using the duty rate in force on each date."
              : "Spot price per gram, before import duty and GST."}
          </p>
        </div>
      )}
    </section>
  );
}
