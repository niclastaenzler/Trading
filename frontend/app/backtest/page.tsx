"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

export default function BacktestPage() {
  const router = useRouter();
  const [symbol, setSymbol] = useState("EURUSD");
  const [bars, setBars] = useState(500);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) router.push("/login");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function run() {
    setBusy(true);
    setResult(await api.backtest(symbol, bars));
    setBusy(false);
  }

  // Tiny inline SVG equity curve (no chart dependency).
  function Curve({ data }: { data: number[] }) {
    if (!data?.length) return null;
    const w = 800, h = 180, min = Math.min(...data), max = Math.max(...data);
    const range = max - min || 1;
    const pts = data
      .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`)
      .join(" ");
    return (
      <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: 180 }}>
        <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="2" />
      </svg>
    );
  }

  return (
    <div>
      <h2>Backtest</h2>
      <div className="card">
        <div className="row">
          <div style={{ flex: 1 }}>
            <label>Symbol</label>
            <input value={symbol} onChange={(e) => setSymbol(e.target.value)} />
          </div>
          <div style={{ flex: 1 }}>
            <label>Bars</label>
            <input type="number" value={bars} onChange={(e) => setBars(parseInt(e.target.value))} />
          </div>
        </div>
        <button style={{ marginTop: 16 }} onClick={run} disabled={busy}>
          {busy ? "Running…" : "Run backtest"}
        </button>
      </div>

      {result && (
        <>
          <div className="grid" style={{ marginTop: 16 }}>
            <div className="card"><h3>Return</h3><div className={`metric ${result.total_return_pct >= 0 ? "pos" : "neg"}`}>{result.total_return_pct}%</div></div>
            <div className="card"><h3>Trades</h3><div className="metric">{result.num_trades}</div></div>
            <div className="card"><h3>Win rate</h3><div className="metric">{(result.win_rate * 100).toFixed(1)}%</div></div>
            <div className="card"><h3>Max drawdown</h3><div className="metric neg">{result.max_drawdown_pct}%</div></div>
            <div className="card"><h3>Sharpe</h3><div className="metric">{result.sharpe}</div></div>
          </div>
          <div className="card" style={{ marginTop: 16 }}>
            <h3>Equity curve</h3>
            <Curve data={result.equity_curve} />
          </div>
        </>
      )}
    </div>
  );
}
