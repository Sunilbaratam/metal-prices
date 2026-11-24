import type { MetalPrice } from "../api";
import { formatINR } from "../format";

export type PriceMode = "retail" | "spot";

interface Props {
  title: string;
  data: MetalPrice;
  mode: PriceMode;
}

export default function PriceCard({ title, data, mode }: Props) {
  const gram = mode === "retail" ? data.retail_per_gram : data.spot_per_gram;
  const ten = mode === "retail" ? data.retail_per_10g : data.spot_per_10g;
  const kg = mode === "retail" ? data.retail_per_kg : data.spot_per_kg;

  const hasChange = data.change !== null && data.change_pct !== null;
  const up = (data.change ?? 0) >= 0;

  return (
    <section className={`card card-${data.metal}`}>
      <header className="card-head">
        <h2>{title}</h2>
        {hasChange && (
          <span className={`chip ${up ? "up" : "down"}`}>
            {up ? "▲" : "▼"} {Math.abs(data.change_pct ?? 0).toFixed(2)}%
          </span>
        )}
      </header>

      <p className="big">
        {formatINR(gram)}
        <span className="unit"> / gram</span>
      </p>

      <dl className="rows">
        <div>
          <dt>Per 10 grams</dt>
          <dd>{formatINR(ten)}</dd>
        </div>
        <div>
          <dt>Per kilogram</dt>
          <dd>{formatINR(kg)}</dd>
        </div>
        <div>
          <dt>International (per troy oz)</dt>
          <dd>{formatINR(data.price_per_oz)}</dd>
        </div>
      </dl>

      {data.by_purity_per_gram && (
        <div className="purity">
          {Object.entries(data.by_purity_per_gram).map(([k, v]) => {
            const shown = mode === "retail" ? v : (v / data.retail_per_gram) * data.spot_per_gram;
            return (
              <div key={k}>
                <span>{k}</span>
                <strong>{formatINR(shown)}</strong>
              </div>
            );
          })}
          <small>per gram</small>
        </div>
      )}
    </section>
  );
}
