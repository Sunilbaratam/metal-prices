import { useMemo, useState } from "react";
import type { LatestResponse, Metal } from "../api";
import { formatINR2 } from "../format";

// GST on making charges for jewellery in India. Check the current rate before relying on it.
const GST_ON_MAKING_PCT = 5;

const SILVER_PURITY: Record<string, number> = { "999 (fine)": 0.999, "925 (sterling)": 0.925 };

export default function Calculator({ latest }: { latest: LatestResponse }) {
  const [metal, setMetal] = useState<Metal>("gold");
  const [goldPurity, setGoldPurity] = useState("22K");
  const [silverPurity, setSilverPurity] = useState("925 (sterling)");
  const [weight, setWeight] = useState("10");
  const [making, setMaking] = useState("12");

  const purityOptions =
    metal === "gold"
      ? Object.keys(latest.gold?.by_purity_per_gram ?? {})
      : Object.keys(SILVER_PURITY);

  const purity = metal === "gold" ? goldPurity : silverPurity;

  const result = useMemo(() => {
    const w = parseFloat(weight);
    const m = parseFloat(making);
    if (!(w > 0) || !(m >= 0)) return null;

    let rate: number | undefined;
    if (metal === "gold") rate = latest.gold?.by_purity_per_gram?.[goldPurity];
    else if (latest.silver) rate = latest.silver.retail_per_gram * (SILVER_PURITY[silverPurity] ?? 1);
    if (rate === undefined) return null;

    const metalValue = rate * w;
    const makingCharge = metalValue * (m / 100);
    const gstMaking = makingCharge * (GST_ON_MAKING_PCT / 100);
    return { rate, metalValue, makingCharge, gstMaking, total: metalValue + makingCharge + gstMaking };
  }, [metal, goldPurity, silverPurity, weight, making, latest]);

  return (
    <section className="panel">
      <h2>Jewellery price calculator</h2>

      <div className="form">
        <label>
          Metal
          <select
            value={metal}
            onChange={(e) => setMetal(e.target.value as Metal)}
          >
            <option value="gold">Gold</option>
            <option value="silver">Silver</option>
          </select>
        </label>

        <label>
          Purity
          <select
            value={purity}
            onChange={(e) =>
              metal === "gold" ? setGoldPurity(e.target.value) : setSilverPurity(e.target.value)
            }
          >
            {purityOptions.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>

        <label>
          Weight (grams)
          <input
            type="number"
            min="0"
            step="0.01"
            inputMode="decimal"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
          />
        </label>

        <label>
          Making charges (%)
          <input
            type="number"
            min="0"
            step="0.5"
            inputMode="decimal"
            value={making}
            onChange={(e) => setMaking(e.target.value)}
          />
        </label>
      </div>

      {result ? (
        <div className="result">
          <div>
            <span>Rate ({purity}) per gram</span>
            <strong>{formatINR2(result.rate)}</strong>
          </div>
          <div>
            <span>Metal value</span>
            <strong>{formatINR2(result.metalValue)}</strong>
          </div>
          <div>
            <span>Making charges</span>
            <strong>{formatINR2(result.makingCharge)}</strong>
          </div>
          <div>
            <span>GST on making ({GST_ON_MAKING_PCT}%)</span>
            <strong>{formatINR2(result.gstMaking)}</strong>
          </div>
          <div className="total">
            <span>Estimated total</span>
            <strong>{formatINR2(result.total)}</strong>
          </div>
        </div>
      ) : (
        <p className="muted">Enter a weight and making charge to see an estimate.</p>
      )}

      <p className="muted small">
        Metal value uses the indicative retail rate (includes import duty and GST on the metal).
        Actual jeweller prices vary by city and shop.
      </p>
    </section>
  );
}
