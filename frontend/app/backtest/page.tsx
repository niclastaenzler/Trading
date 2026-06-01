"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

// Charts touch the DOM/canvas, so load client-side only.
const EquityChart = dynamic(() => import("@/app/components/EquityChart"), {
  ssr: false,
});

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
            <div className="card"><h3>Sortino</h3><div className="metric">{result.sortino}</div></div>
            <div className="card"><h3>Profit factor</h3><div className="metric">{result.profit_factor}</div></div>
            <div className="card"><h3>Avg win / loss</h3><div className="metric"><span className="pos">{result.avg_win}</span> / <span className="neg">{result.avg_loss}</span></div></div>
          </div>
          <div className="card" style={{ marginTop: 16 }}>
            <h3>Equity curve</h3>
            <EquityChart data={result.equity_curve} />
          </div>
        </>
      )}
    </div>
  );
}
