"use client";

import { useEffect, useRef, useState } from "react";
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
  const [live, setLive] = useState(false);

  // Refs keep the WebSocket handler pointing at the latest refresh() without
  // re-opening the socket, and debounce burst events into one KPI refresh.
  const refreshRef = useRef<() => void>(() => {});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function refresh() {
    setPerf(await api.performance());
    setCfg(await api.getConfig());
    setPending((await api.pending()).pending || []);
  }
  refreshRef.current = refresh;

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    refresh();
    const ws = new WebSocket(wsUrl());
    ws.onopen = () => setLive(true);
    ws.onclose = () => setLive(false);
    ws.onmessage = (ev) => {
      let line = String(ev.data);
      let isTradeEvent = false;
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "order_placed") {
          line = `🟢 ORDER ${msg.side} ${msg.symbol} @ ${msg.price} (${msg.mode})`;
          isTradeEvent = true;
        } else if (msg.type === "position_closed") {
          line = `🔴 CLOSED ${msg.symbol} @ ${msg.exit_price}  pnl=${msg.pnl} (${msg.reason})`;
          isTradeEvent = true;
        } else if (msg.signal) {
          const s = msg.signal;
          const dir = s.direction > 0 ? "BUY" : s.direction < 0 ? "SELL" : "—";
          line = `📡 ${msg.symbol} ${dir} conf ${(s.confidence * 100).toFixed(0)}%`;
        }
      } catch {
        /* keep raw line */
      }
      setFeed((f) => [`${new Date().toLocaleTimeString()}  ${line}`, ...f].slice(0, 60));
      // A trade changed account state -> refresh the KPI cards live (debounced).
      if (isTradeEvent) {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => refreshRef.current(), 500);
      }
    };
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      ws.close();
    };
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
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>Live signal &amp; event feed</span>
          <span className={`live-dot ${live ? "on" : "off"}`}>
            {live ? "LIVE" : "offline"}
          </span>
        </h3>
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
