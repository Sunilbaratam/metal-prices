export type Metal = "gold" | "silver";
export type HistoryRange = "1w" | "1m" | "3m" | "6m" | "1y";

export interface MetalPrice {
  metal: Metal;
  currency: string;
  updated_at: string;
  price_per_oz: number;
  spot_per_gram: number;
  spot_per_10g: number;
  spot_per_kg: number;
  retail_per_gram: number;
  retail_per_10g: number;
  retail_per_kg: number;
  change: number | null;
  change_pct: number | null;
  by_purity_per_gram?: Record<string, number>;
}

export interface LatestResponse {
  gold?: MetalPrice;
  silver?: MetalPrice;
  updated_at: string;
  stale_after_hours: number;
  note: string;
}

export interface HistoryPoint {
  date: string;
  spot_per_gram: number;
  retail_per_gram: number; // spot + the import duty in force on that date + GST
  duty_pct: number;
  per_oz: number;
}

export interface HistoryResponse {
  metal: Metal;
  range: HistoryRange;
  points: HistoryPoint[];
}

const RANGE_DAYS: Record<HistoryRange, number> = { "1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365 };

// The daily GitHub job publishes these files next to the page (see data/ in the built site).
async function getJson<T>(file: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${file}`, { cache: "no-cache" });
  if (!res.ok) {
    throw new Error(
      res.status === 404 ? "No price data published yet." : `Couldn't load prices (${res.status})`,
    );
  }
  return res.json() as Promise<T>;
}

export const fetchLatest = () => getJson<LatestResponse>("latest.json");

// One file holds up to a year per metal; shorter ranges are cut here.
export async function fetchHistory(metal: Metal, range: HistoryRange): Promise<HistoryResponse> {
  const data = await getJson<HistoryResponse>(`history_${metal}.json`);
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - RANGE_DAYS[range]);
  const cutoffDay = cutoff.toISOString().slice(0, 10);
  return { ...data, range, points: data.points.filter((p) => p.date >= cutoffDay) };
}
