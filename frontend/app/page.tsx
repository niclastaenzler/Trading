"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { api, getToken, wsUrl } from "@/lib/api";

const EquityChart = dynamic(() => import("@/app/components/EquityChart"), {
  ssr: false,
});

export default function Dashboard() {
  const router = useRouter();
  const [perf, setPerf] = useState<any>(null);
  const [cfg, setCfg] = useState<any>(null);
  const [pending, setPending] = useState<any[]>([]);
  const [feed, setFeed] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setPerf(await api.performance());
    setCfg(await api.getConfig());
    setPending((await api.pending()).pending || []);
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    refresh();
    const ws = new WebSocket(wsUrl());
    ws.onmessage = (ev) => {
      setFeed((f) => [`${new Date().toLocaleTimeString()}  ${ev.data}`, ...f].slice(0, 50));
    };
    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggle() {
    setBusy(true);
    await api.toggleAutomation(!cfg.auto_trading_enabled);
    await refresh();
    setBusy(false);
  }
  async function kill(activate: boolean) {
    setBusy(true);
    await api.killSwitch(activate);
    await refresh();
    setBusy(false);
  }
  async function runCycle() {
    setBusy(true);
    await api.runCycle();
    await refresh();
    setBusy(false);
  }
  async function decide(symbol: string, approve: boolean) {
    await api.confirm(symbol, approve);
    await refresh();
  }

  if (!perf || !cfg) return <p>Loading…</p>;

  return (
    <div>
      {cfg.kill_switch_active && (
        <div className="banner">🛑 KILL SWITCH ACTIVE — all automated trading is halted.</div>
      )}

      <div className="row" style={{ marginBottom: 16 }}>
        <span>
          Auto-trading:{" "}
          <span className={`pill ${cfg.auto_trading_enabled ? "on" : "off"}`}>
            {cfg.auto_trading_enabled ? "ON" : "OFF"}
          </span>
        </span>
        <button className="secondary" onClick={toggle} disabled={busy || cfg.kill_switch_active}>
          {cfg.auto_trading_enabled ? "Disable" : "Enable"} auto-trading
        </button>
        <button className="secondary" onClick={runCycle} disabled={busy}>
          Run cycle now
        </button>
        {cfg.kill_switch_active ? (
          <button className="secondary" onClick={() => kill(false)} disabled={busy}>
            Clear kill switch
          </button>
        ) : (
          <button className="danger" onClick={() => kill(true)} disabled={busy}>
            🛑 Kill switch
          </button>
        )}
      </div>

      <div className="grid">
        <div className="card">
          <h3>Equity</h3>
          <div className="metric">${perf.equity?.toLocaleString()}</div>
        </div>
        <div className="card">
          <h3>Open positions</h3>
          <div className="metric">{perf.open_positions}</div>
        </div>
        <div className="card">
          <h3>Total trades</h3>
          <div className="metric">{perf.total_trades}</div>
        </div>
        <div className="card">
          <h3>Win rate</h3>
          <div className="metric">{(perf.win_rate * 100).toFixed(1)}%</div>
        </div>
        <div className="card">
          <h3>Total PnL</h3>
          <div className={`metric ${perf.total_pnl >= 0 ? "pos" : "neg"}`}>
            ${perf.total_pnl?.toFixed(2)}
          </div>
        </div>
        <div className="card">
          <h3>Profit factor</h3>
          <div className="metric">{perf.profit_factor}</div>
        </div>
        <div className="card">
          <h3>PnL today</h3>
          <div className={`metric ${perf.realized_pnl_today >= 0 ? "pos" : "neg"}`}>
            ${perf.realized_pnl_today?.toFixed(2)}
          </div>
        </div>
      </div>

      {perf.equity_curve?.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Realized PnL curve</h3>
          <EquityChart data={perf.equity_curve} color="#2ecc71" />
        </div>
      )}

      {pending.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Pending confirmations (semi-auto)</h3>
          <table>
            <thead>
              <tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>SL</th><th>TP</th><th></th></tr>
            </thead>
            <tbody>
              {pending.map((p, i) => (
                <tr key={i}>
                  <td>{p.plan.symbol}</td>
                  <td>{p.plan.side}</td>
                  <td>{p.plan.quantity}</td>
                  <td>{p.plan.entry_price}</td>
                  <td>{p.plan.stop_loss}</td>
                  <td>{p.plan.take_profit}</td>
                  <td className="row">
                    <button onClick={() => decide(p.plan.symbol, true)}>Approve</button>
                    <button className="danger" onClick={() => decide(p.plan.symbol, false)}>
                      Reject
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Live signal & event feed</h3>
        <div className="feed">
          {feed.length === 0 && <div>Waiting for events…</div>}
          {feed.map((line, i) => (
            <div key={i}>{line}</div>
          ))}
        </div>
      </div>
    </div>
  );
}
