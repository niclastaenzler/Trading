"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { api, getToken, wsUrl } from "@/lib/api";

const EquityChart = dynamic(() => import("@/app/components/EquityChart"), { ssr: false });
const CandleChart = dynamic(() => import("@/app/components/CandleChart"), { ssr: false });

const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"];

export default function Dashboard() {
  const router = useRouter();
  const [perf, setPerf] = useState<any>(null);
  const [cfg, setCfg] = useState<any>(null);
  const [account, setAccount] = useState<any>(null);
  const [pending, setPending] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [recentTrades, setRecentTrades] = useState<any[]>([]);
  const [feed, setFeed] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [cycleMsg, setCycleMsg] = useState("");

  // Live trading view state.
  const [symbol, setSymbol] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState("1h");
  const [candles, setCandles] = useState<any[]>([]);
  const [lastPrice, setLastPrice] = useState<number | null>(null);

  // KI-Marktanalyse (portfolio scan).
  const [scan, setScan] = useState<any[]>([]);
  const [scanning, setScanning] = useState(false);
  async function loadScan() {
    setScanning(true);
    try { setScan((await api.scan()).opportunities || []); } catch { setScan([]); }
    setScanning(false);
  }

  const refreshRef = useRef<() => void>(() => {});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function refresh() {
    setPerf(await api.performance());
    setCfg(await api.getConfig());
    setPending((await api.pending()).pending || []);
    try { setAccount(await api.account()); } catch { setAccount(null); }
    try { setPositions(await api.positions()); } catch { setPositions([]); }
    try { setRecentTrades((await api.trades()).slice(0, 5)); } catch { setRecentTrades([]); }
  }
  refreshRef.current = refresh;

  async function loadCandles() {
    try {
      const r = await api.candles(symbol, timeframe, 200);
      setCandles(r.candles || []);
      if (r.candles?.length) setLastPrice(r.candles[r.candles.length - 1].close);
    } catch {
      setCandles([]);
    }
  }

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    refresh();
    loadScan();
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
          line = `🔴 GESCHLOSSEN ${msg.symbol} @ ${msg.exit_price}  PnL=${msg.pnl} (${msg.reason})`;
          isTradeEvent = true;
        } else if (msg.signal) {
          const s = msg.signal;
          const dir = s.direction > 0 ? "KAUF" : s.direction < 0 ? "VERKAUF" : "—";
          line = `📡 ${msg.symbol} ${dir} Konfidenz ${(s.confidence * 100).toFixed(0)}%`;
        }
      } catch { /* roh */ }
      setFeed((f) => [`${new Date().toLocaleTimeString()}  ${line}`, ...f].slice(0, 60));
      if (isTradeEvent) {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => refreshRef.current(), 500);
      }
    };
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); ws.close(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load + auto-refresh the chart (every 30s) and when symbol/timeframe change.
  useEffect(() => {
    loadCandles();
    const id = setInterval(loadCandles, 30000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, timeframe]);

  async function toggle() { setBusy(true); await api.toggleAutomation(!cfg.auto_trading_enabled); await refresh(); setBusy(false); }
  async function kill(activate: boolean) { setBusy(true); await api.killSwitch(activate); await refresh(); setBusy(false); }
  // German labels for cycle outcomes, so the user sees WHY nothing executed.
  const REASONS: Record<string, string> = {
    "outside trading session": "außerhalb der Handelszeit",
    "trade cadence cooldown": "Abkühlzeit zwischen Trades",
    "max trades per hour reached": "max. Trades/Stunde erreicht",
    "max trades per day reached": "max. Trades/Tag erreicht",
    "high volatility halt": "Stopp wegen hoher Volatilität",
    "kill switch active": "Not-Aus aktiv",
    "auto-trading disabled": "Auto-Handel ist aus",
  };
  async function runCycle() {
    setBusy(true);
    setCycleMsg("");
    try {
      const r = await api.runCycle();
      const res: any[] = r.results || [];
      const exec = res.filter((x) => x.action === "executed").length;
      const pend = res.filter((x) => x.action === "pending").length;
      const none = res.filter((x) => x.action === "none").length;
      const blocked = res.filter((x) => x.action === "blocked");
      const parts: string[] = [];
      if (exec) parts.push(`${exec} ausgeführt`);
      if (pend) parts.push(`${pend} wartet auf Bestätigung (siehe unten)`);
      if (none) parts.push(`${none}× kein Signal`);
      if (blocked.length) {
        const reasons = Array.from(new Set(blocked.map((b) => REASONS[b.reason] || b.reason)));
        parts.push(`${blocked.length}× blockiert: ${reasons.join(", ")}`);
      }
      if (r.closed?.length) parts.push(`${r.closed.length} Position(en) geschlossen`);
      setCycleMsg(parts.length ? parts.join(" · ") : "Zyklus gelaufen — nichts zu tun.");
    } catch (e: any) {
      setCycleMsg("Fehler: " + e.message);
    }
    await refresh();
    await loadCandles();
    setBusy(false);
  }
  async function decide(s: string, approve: boolean) { await api.confirm(s, approve); await refresh(); }
  async function close(s: string) { setBusy(true); await api.closePosition(s); await refresh(); setBusy(false); }

  if (!perf || !cfg) return <p>Lädt…</p>;

  const symbolOptions: string[] =
    cfg.config?.trading?.allowed_symbols?.length
      ? cfg.config.trading.allowed_symbols
      : ["EURUSD", "GBPUSD", "BTCUSD"];

  return (
    <div>
      {cfg.kill_switch_active && (
        <div className="banner">🛑 NOT-AUS AKTIV — der automatische Handel ist gestoppt.</div>
      )}

      <div className="row" style={{ marginBottom: 16 }}>
        <span>
          Auto-Handel:{" "}
          <span className={`pill ${cfg.auto_trading_enabled ? "on" : "off"}`}>
            {cfg.auto_trading_enabled ? "AN" : "AUS"}
          </span>
        </span>
        <button className="secondary" onClick={toggle} disabled={busy || cfg.kill_switch_active}>
          Auto-Handel {cfg.auto_trading_enabled ? "ausschalten" : "einschalten"}
        </button>
        <button className="secondary" onClick={runCycle} disabled={busy}>Zyklus jetzt ausführen</button>
        {cfg.kill_switch_active ? (
          <button className="secondary" onClick={() => kill(false)} disabled={busy}>Not-Aus aufheben</button>
        ) : (
          <button className="danger" onClick={() => kill(true)} disabled={busy}>🛑 Not-Aus</button>
        )}
      </div>

      {cycleMsg && (
        <div className="banner" style={{ borderColor: "var(--accent)", color: "var(--text)", background: "rgba(76,139,245,.1)", marginBottom: 16 }}>
          Zyklus-Ergebnis: {cycleMsg}
        </div>
      )}

      {/* Konto-Übersicht */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3>Konto</h3>
        {account?.ok ? (
          <div className="row" style={{ gap: 28 }}>
            <div><div style={{ color: "var(--muted)", fontSize: 12 }}>BROKER</div><b>{account.broker}</b></div>
            <div><div style={{ color: "var(--muted)", fontSize: 12 }}>MODUS</div>
              <span className={`pill ${account.is_paper ? "off" : "on"}`}>{account.mode}</span></div>
            <div><div style={{ color: "var(--muted)", fontSize: 12 }}>KONTOSTAND</div><b>{account.balance?.toLocaleString()}</b></div>
            <div><div style={{ color: "var(--muted)", fontSize: 12 }}>OFFENE POS.</div><b>{account.open_positions}</b></div>
            <div><div style={{ color: "var(--muted)", fontSize: 12 }}>NICHT REAL. PnL</div>
              <b className={account.unrealized_pnl >= 0 ? "pos" : "neg"}>{account.unrealized_pnl}</b></div>
          </div>
        ) : (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>
            Kein Broker verbunden / nicht erreichbar. Unter <b>Einstellungen</b> Capital.com verbinden.
          </p>
        )}
      </div>

      {/* Live Trading View */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>Live-Trading-Ansicht — {symbol} {lastPrice ? `· ${lastPrice}` : ""}</span>
          <span className="row">
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} style={{ width: "auto" }}>
              {symbolOptions.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} style={{ width: "auto" }}>
              {TIMEFRAMES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <button className="secondary" onClick={loadCandles}>↻</button>
          </span>
        </h3>
        {candles.length ? <CandleChart data={candles} /> : <p style={{ color: "var(--muted)" }}>Lade Kurse…</p>}
        <p style={{ color: "var(--muted)", fontSize: 12, marginBottom: 0 }}>
          Aktualisiert automatisch alle 30 s. Datenquelle: dein verbundener Broker (sonst simuliert).
        </p>
      </div>

      {/* KI-Marktanalyse: was die KI handeln will */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>🤖 KI-Marktanalyse — was gehandelt werden soll</span>
          <button className="secondary" onClick={loadScan} disabled={scanning}>
            {scanning ? "Scanne…" : "Markt scannen"}
          </button>
        </h3>
        <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 0 }}>
          Die KI bewertet alle konfigurierten Instrumente und sortiert nach Konfidenz.
          Grün = handelbares Signal. Die Engine handelt die stärksten zuerst (begrenzt
          durch „max. offene Positionen" &amp; Risiko).
        </p>
        {scan.length === 0 ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>
            {scanning ? "Analysiere Markt…" : "Noch keine Analyse — auf »Markt scannen« klicken."}
          </p>
        ) : (
          <table>
            <thead>
              <tr><th>#</th><th>Symbol</th><th>Signal</th><th>Konfidenz</th><th>Preis</th><th>Status</th></tr>
            </thead>
            <tbody>
              {scan.slice(0, 25).map((o, i) => (
                <tr key={o.symbol} style={o.actionable ? { background: "rgba(46,204,113,.06)" } : {}}>
                  <td>{i + 1}</td>
                  <td><b>{o.symbol}</b></td>
                  <td className={o.direction > 0 ? "pos" : o.direction < 0 ? "neg" : ""}>
                    {o.action === "BUY" ? "KAUF" : o.action === "SELL" ? "VERKAUF" : "—"}
                  </td>
                  <td>{(o.confidence * 100).toFixed(0)}%</td>
                  <td>{o.price}</td>
                  <td>
                    {o.actionable
                      ? <span className="pill on">handelbar</span>
                      : <span style={{ color: "var(--muted)", fontSize: 12 }}>{o.reason}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Kennzahlen */}
      <div className="grid">
        <div className="card"><h3>Equity</h3><div className="metric">{perf.equity?.toLocaleString()}</div></div>
        <div className="card"><h3>Offene Positionen</h3><div className="metric">{perf.open_positions}</div></div>
        <div className="card"><h3>Trades gesamt</h3><div className="metric">{perf.total_trades}</div></div>
        <div className="card"><h3>Trefferquote</h3><div className="metric">{(perf.win_rate * 100).toFixed(1)}%</div></div>
        <div className="card"><h3>Gesamt-PnL</h3><div className={`metric ${perf.total_pnl >= 0 ? "pos" : "neg"}`}>{perf.total_pnl?.toFixed(2)}</div></div>
        <div className="card"><h3>Profit-Faktor</h3><div className="metric">{perf.profit_factor}</div></div>
        <div className="card"><h3>PnL heute</h3><div className={`metric ${perf.realized_pnl_today >= 0 ? "pos" : "neg"}`}>{perf.realized_pnl_today?.toFixed(2)}</div></div>
      </div>

      {perf.equity_curve?.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Realisierte PnL-Kurve</h3>
          <EquityChart data={perf.equity_curve} color="#2ecc71" />
        </div>
      )}

      {pending.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Offene Bestätigungen (Halb-Automatik)</h3>
          <table>
            <thead><tr><th>Symbol</th><th>Seite</th><th>Menge</th><th>Einstieg</th><th>SL</th><th>TP</th><th></th></tr></thead>
            <tbody>
              {pending.map((p, i) => (
                <tr key={i}>
                  <td>{p.plan.symbol}</td><td>{p.plan.side}</td><td>{p.plan.quantity}</td>
                  <td>{p.plan.entry_price}</td><td>{p.plan.stop_loss}</td><td>{p.plan.take_profit}</td>
                  <td className="row">
                    <button onClick={() => decide(p.plan.symbol, true)}>Annehmen</button>
                    <button className="danger" onClick={() => decide(p.plan.symbol, false)}>Ablehnen</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Offene Positionen ({positions.length})</h3>
        {positions.length === 0 ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>
            Keine offenen Positionen. Trades erscheinen hier, sobald die Engine eine eröffnet —
            <b> Auto-Handel</b> einschalten und <b>Zyklus jetzt ausführen</b> (in Halb-Automatik die
            Bestätigung oben annehmen).
          </p>
        ) : (
          <table>
            <thead><tr><th>Symbol</th><th>Seite</th><th>Menge</th><th>Einstieg</th><th>Aktuell</th><th>uPnL</th><th>SL</th><th>TP</th><th></th></tr></thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={i}>
                  <td>{p.symbol}</td><td>{p.side}</td><td>{p.quantity}</td><td>{p.entry_price}</td>
                  <td>{p.current_price}</td>
                  <td className={p.unrealized_pnl >= 0 ? "pos" : "neg"}>{p.unrealized_pnl}</td>
                  <td>{p.stop_loss ?? "—"}</td><td>{p.take_profit ?? "—"}</td>
                  <td><button className="danger" onClick={() => close(p.symbol)} disabled={busy}>Schließen</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>Letzte Trades</span>
          <a href="/Trading/trades/" style={{ fontSize: 13 }}>Alle anzeigen →</a>
        </h3>
        {recentTrades.length === 0 ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>Noch keine Trades.</p>
        ) : (
          <table>
            <thead><tr><th>Symbol</th><th>Seite</th><th>Einstieg</th><th>Ausstieg</th><th>PnL</th><th>Status</th></tr></thead>
            <tbody>
              {recentTrades.map((t) => (
                <tr key={t.id}>
                  <td>{t.symbol}</td><td>{t.side}</td><td>{t.entry_price}</td><td>{t.exit_price ?? "—"}</td>
                  <td className={t.pnl >= 0 ? "pos" : "neg"}>{t.pnl?.toFixed?.(2) ?? "—"}</td>
                  <td><span className={`pill ${t.status === "OPEN" ? "on" : "off"}`}>{t.status === "OPEN" ? "OFFEN" : "ZU"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>Live Signal- &amp; Ereignis-Feed</span>
          <span className={`live-dot ${live ? "on" : "off"}`}>{live ? "LIVE" : "offline"}</span>
        </h3>
        <div className="feed">
          {feed.length === 0 && <div>Warte auf Ereignisse…</div>}
          {feed.map((line, i) => <div key={i}>{line}</div>)}
        </div>
      </div>
    </div>
  );
}
