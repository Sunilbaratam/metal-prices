import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchLatest } from "./api";
import { formatDateTimeIST, timeAgo } from "./format";
import PriceCard, { type PriceMode } from "./components/PriceCard";
import HistoryChart from "./components/HistoryChart";
import Calculator from "./components/Calculator";

export default function App() {
  const [mode, setMode] = useState<PriceMode>("retail");

  // Prices are published once a day, so checking every few minutes is plenty.
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["latest"],
    queryFn: fetchLatest,
    refetchInterval: 5 * 60_000,
  });

  // Worked out here (not stored) so the warning still appears if the daily job ever stops.
  const stale =
    !!data && Date.now() - new Date(data.updated_at).getTime() > data.stale_after_hours * 3_600_000;

  return (
    <div className="wrap">
      <header className="top">
        <div>
          <h1>Gold &amp; Silver Price Today</h1>
          <p className="muted">India · prices in ₹ (INR)</p>
        </div>

        <div className="seg" role="group" aria-label="Price type">
          <button className={mode === "retail" ? "on" : ""} onClick={() => setMode("retail")}>
            Retail (incl. duty &amp; GST)
          </button>
          <button className={mode === "spot" ? "on" : ""} onClick={() => setMode("spot")}>
            Spot
          </button>
        </div>
      </header>

      {isLoading && <p className="muted">Loading prices…</p>}

      {isError && (
        <div className="banner error">
          {error instanceof Error ? error.message : "Couldn't load prices."}
        </div>
      )}

      {data && (
        <>
          <p className="updated">
            Last updated: {formatDateTimeIST(data.updated_at)} ({timeAgo(data.updated_at)})
          </p>

          {stale && (
            <div className="banner warn">
              These prices may be out of date. We couldn't refresh them recently.
            </div>
          )}

          <div className="grid">
            {data.gold && <PriceCard title="Gold" data={data.gold} mode={mode} />}
            {data.silver && <PriceCard title="Silver" data={data.silver} mode={mode} />}
          </div>

          <HistoryChart mode={mode} />
          <Calculator latest={data} />

          <footer className="foot">
            <p>
              <strong>Disclaimer:</strong> {data.note} Prices are updated once a day and are not for
              trading decisions. Check with your jeweller for the rate you will actually pay.
            </p>
          </footer>
        </>
      )}
    </div>
  );
}
