"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { api, getToken, wsUrl } from "@/lib/api";

const EquityChart = dynamic(() => import("@/app/components/EquityChart"), { ssr: false });
const CandleChart = dynamic(() => import("@/app/components/CandleChart"), { ssr: false });

const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"];

// Small horizontal bar (0..1) for visualising the AI's reasoning.
function Bar({ value, color = "var(--accent)", label }: { value: number; color?: string; label?: string }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div style={{ margin: "4px 0" }}>
      {label && (
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--muted)" }}>
          <span>{label}</span><span className="mono">{pct.toFixed(0)}%</span>
        </div>
      )}
      <div style={{ height: 8, background: "var(--panel-2)", borderRadius: 6, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, transition: "width .3s" }} />
      </div>
    </div>
  );
}

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
  const [candleSource, setCandleSource] = useState<{ source: string; live: boolean } | null>(null);

  // KI-Denkweise (Reasoning) für das gewählte Symbol.
  const [think, setThink] = useState<any>(null);
  async function loadThink() { try { setThink(await api.explain(symbol)); } catch { setThink(null); } }

  // KI-Marktanalyse (portfolio scan).
  const [scan, setScan] = useState<any[]>([]);
  const [scanning, setScanning] = useState(false);
  async function loadScan() {
    setScanning(true);
    try { setScan((await api.scan()).opportunities || []); } catch { setScan([]); }
    setScanning(false);
  }

  // Ehrliche Edge-Bewertung (Walk-Forward) für das aktuell gewählte Symbol.
  const [edgeEval, setEdgeEval] = useState<any>(null);
  const [edgeBusy, setEdgeBusy] = useState(false);
  async function runEdge() {
    setEdgeBusy(true);
    try { setEdgeEval(await api.edgeEval(symbol)); } catch (e: any) { setEdgeEval({ ok: false, error: e.message }); }
    setEdgeBusy(false);
  }

  // KI-Modell-Training (gepooltes Multi-Asset-Modell) + Status.
  const [model, setModel] = useState<any>(null);
  const [training, setTraining] = useState(false);
  async function loadModel() { try { setModel(await api.modelStatus()); } catch { setModel(null); } }
  async function trainModel() {
    setTraining(true);
    try {
      const r = await api.trainModel();
      if (r.ok === false) setModel({ ...(model || {}), error: r.error });
      else await loadModel();
    } catch (e: any) {
      setModel({ ...(model || {}), error: e.message });
    }
    setTraining(false);
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
      setCandleSource({ source: r.source, live: r.live });
      if (r.candles?.length) setLastPrice(r.candles[r.candles.length - 1].close);
    } catch {
      setCandles([]);
      setCandleSource(null);
    }
  }

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    refresh();
    loadScan();
    loadModel();
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
    loadThink();
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
      if (pend) parts.push(`${pend} wartet auf Bestätigung (unten „Annehmen")`);
      if (none) {
        // Show WHY nothing was actionable (dominant reason across symbols).
        const reasons = res.filter((x) => x.action === "none").map((x) => x.reason || "kein Signal");
        const counts: Record<string, number> = {};
        reasons.forEach((rs) => (counts[rs] = (counts[rs] || 0) + 1));
        const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${v}× ${k}`);
        parts.push(`kein handelbares Setup (${top.join(", ")})`);
      }
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

      {/* Konto-Ticker (Platform-Header) */}
      <div className="ticker">
        <div className="tk">
          <span className="lbl">KONTOSTAND</span>
          <span className="val mono">{(account?.balance ?? perf.equity)?.toLocaleString()} </span>
        </div>
        <div className="sep" />
        <div className="tk">
          <span className="lbl">NICHT REAL. PnL</span>
          <span className={`val mono ${(account?.unrealized_pnl ?? 0) >= 0 ? "pos" : "neg"}`}>
            {account?.unrealized_pnl ?? 0}
          </span>
        </div>
        <div className="tk">
          <span className="lbl">PnL HEUTE</span>
          <span className={`val mono ${perf.realized_pnl_today >= 0 ? "pos" : "neg"}`}>
            {perf.realized_pnl_today?.toFixed(2)}
          </span>
        </div>
        <div className="tk">
          <span className="lbl">GESAMT-PnL</span>
          <span className={`val mono ${perf.total_pnl >= 0 ? "pos" : "neg"}`}>{perf.total_pnl?.toFixed(2)}</span>
        </div>
        <div className="sep" />
        <div className="tk">
          <span className="lbl">OFFENE POS.</span>
          <span className="val mono">{account?.open_positions ?? perf.open_positions}</span>
        </div>
        <div className="tk">
          <span className="lbl">BROKER</span>
          <span className="val" style={{ fontSize: 15 }}>
            {account?.broker ?? "—"}{" "}
            <span className={`pill ${account?.is_paper === false ? "on" : "off"}`} style={{ fontSize: 10 }}>
              {account?.mode ?? "—"}
            </span>
          </span>
        </div>
        <div className="sep" />
        <div className="tk">
          <span className="lbl">AUTO-HANDEL</span>
          <span className={`val ${cfg.auto_trading_enabled ? "pos" : "neg"}`} style={{ fontSize: 15 }}>
            {cfg.auto_trading_enabled ? "● AKTIV" : "○ AUS"}
          </span>
        </div>
      </div>

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

      {/* Live Trading View */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>
            Live-Trading-Ansicht — {symbol} {lastPrice ? `· ${lastPrice}` : ""}
            {candleSource && (
              <span className={`pill ${candleSource.live ? "on" : "off"}`} style={{ marginLeft: 10, fontSize: 11 }}>
                {candleSource.live ? `● ${candleSource.source}` : "simuliert"}
              </span>
            )}
          </span>
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

      {/* KI-Denkweise (Reasoning) */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>🧠 KI-Denkweise — {symbol}</span>
          <button className="secondary" onClick={loadThink}>↻</button>
        </h3>
        {!think ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>Lade KI-Begründung…</p>
        ) : (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
            {/* 1. KI-Wahrscheinlichkeiten */}
            <div>
              <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 6 }}>KI-WAHRSCHEINLICHKEIT</div>
              {think.ai ? (
                <>
                  <Bar label="Kaufen" value={think.ai.probabilities?.buy ?? 0} color="var(--green)" />
                  <Bar label="Verkaufen" value={think.ai.probabilities?.sell ?? 0} color="var(--red)" />
                  <Bar label="Halten" value={think.ai.probabilities?.hold ?? 0} color="var(--muted)" />
                </>
              ) : <p style={{ color: "var(--muted)", fontSize: 12 }}>KI-Modell deaktiviert.</p>}
            </div>

            {/* 2. Komponenten */}
            <div>
              <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 6 }}>KOMPONENTEN (Stimmen)</div>
              <div style={{ fontSize: 13, lineHeight: 1.9 }}>
                <div>🤖 KI: <b className={think.ai?.direction > 0 ? "pos" : think.ai?.direction < 0 ? "neg" : ""}>
                  {think.ai ? (think.ai.direction > 0 ? "Kauf" : think.ai.direction < 0 ? "Verkauf" : "neutral") : "—"}</b>
                  {think.ai ? ` (${(think.ai.confidence * 100).toFixed(0)}%)` : ""}</div>
                <div>📊 Muster: <b>{think.pattern?.name || "—"}</b>
                  {think.pattern ? ` (${(think.pattern.strength * 100).toFixed(0)}%)` : ""}</div>
                <div>📈 Trend: <b className={think.trend > 0 ? "pos" : think.trend < 0 ? "neg" : ""}>
                  {think.trend > 0 ? "aufwärts" : think.trend < 0 ? "abwärts" : "seitwärts"}</b></div>
                {think.sentiment != null && <div>📰 Sentiment: <b>{think.sentiment}</b></div>}
              </div>
            </div>

            {/* 3. Marktregime */}
            <div>
              <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 6 }}>MARKTREGIME</div>
              <Bar label="Trendstärke" value={think.regime?.trend_strength ?? 0} color="var(--accent)" />
              <Bar label="Volatilität (Perzentil)" value={think.regime?.volatility_percentile ?? 0} color="#e0a13c" />
              <div style={{ fontSize: 13, marginTop: 6 }}>
                Regime: <b>{think.regime?.regime === "trend" ? "📈 Trend" : "↔ Seitwärts"}</b>
                {think.regime?.higher_high && " · höheres Hoch"}
                {think.regime?.lower_low && " · tieferes Tief"}
              </div>
            </div>

            {/* 4. Entscheidungs-Kette */}
            <div>
              <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 6 }}>ENTSCHEIDUNG</div>
              <div className="row" style={{ marginBottom: 6 }}>
                <span className={`pill ${think.actionable ? "on" : "off"}`}>
                  {think.action} {think.actionable ? "✓ handelbar" : "kein Trade"}
                </span>
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.8 }}>
                {think.decision_chain.map((s: any, i: number) => (
                  <div key={i}>
                    <span style={{ color: s.ok ? "var(--green)" : "var(--red)" }}>{s.ok ? "✓" : "✗"}</span>{" "}
                    {s.step} <span style={{ color: "var(--muted)", fontSize: 12 }}>· {s.detail}</span>
                  </div>
                ))}
                <div style={{ marginTop: 4 }}>Edge-Score: <b>{(think.edge_score * 100).toFixed(0)}</b> / 100</div>
              </div>
            </div>
          </div>
        )}
        <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 10, marginBottom: 0 }}>
          So „denkt" die KI: Sie kombiniert die KI-Wahrscheinlichkeit, Muster und Trend zu einer
          Konfidenz, prüft Marktregime/Volatilität und entscheidet über die Entscheidungs-Kette.
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
              <tr><th>#</th><th>Symbol</th><th>Signal</th><th>Konfidenz</th><th>Edge-Score</th><th>Rel. Stärke</th><th>Hebel</th><th>Einsatz</th><th>Regime</th><th>Status</th></tr>
            </thead>
            <tbody>
              {scan.slice(0, 25).map((o, i) => (
                <tr key={o.symbol} className={o.actionable ? "win" : ""}>
                  <td>{i + 1}</td>
                  <td><b>{o.symbol}</b></td>
                  <td className={o.direction > 0 ? "pos" : o.direction < 0 ? "neg" : ""}>
                    {o.action === "BUY" ? "KAUF" : o.action === "SELL" ? "VERKAUF" : "—"}
                  </td>
                  <td>{(o.confidence * 100).toFixed(0)}%</td>
                  <td><b>{((o.edge_score ?? 0) * 100).toFixed(0)}</b></td>
                  <td>{o.rel_strength != null ? (o.rel_strength * 100).toFixed(0) + "%" : "—"}</td>
                  <td className="mono">{o.leverage != null ? o.leverage + "×" : "—"}</td>
                  <td className="mono">{o.risk_eur != null ? o.risk_eur + " €" : "—"}</td>
                  <td>{o.regime === "trend" ? "📈 Trend" : o.regime === "range" ? "↔ Seitwärts" : "—"}</td>
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

      {/* KI-Modell-Training */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>🧠 KI-Modell (gepooltes Multi-Asset-Training)</span>
          <button className="secondary" onClick={trainModel} disabled={training}>
            {training ? "Trainiere…" : "Modell trainieren"}
          </button>
        </h3>
        <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 0 }}>
          Trainiert ein gemeinsames Modell über alle konfigurierten Märkte (echte
          Broker-Historie, wenn verbunden). Wird in der Datenbank gespeichert und
          übersteht Neustarts.
        </p>
        {model?.error && <div className="banner">{model.error}</div>}
        {model ? (
          <div className="row" style={{ gap: 24 }}>
            <div><div style={{ color: "var(--muted)", fontSize: 12 }}>STATUS</div>
              <span className={`pill ${model.is_trained ? "on" : "off"}`}>{model.is_trained ? "trainiert" : "Heuristik"}</span></div>
            <div><div style={{ color: "var(--muted)", fontSize: 12 }}>ZULETZT</div><b>{model.trained_at ? new Date(model.trained_at).toLocaleString() : "—"}</b></div>
            <div><div style={{ color: "var(--muted)", fontSize: 12 }}>OUT-OF-SAMPLE</div><b>{model.metrics?.test_score != null ? (model.metrics.test_score * 100).toFixed(1) + "%" : "—"}</b></div>
            <div><div style={{ color: "var(--muted)", fontSize: 12 }}>INSTRUMENTE</div><b>{model.metrics?.instruments ?? "—"}</b></div>
          </div>
        ) : <p style={{ color: "var(--muted)", fontSize: 13 }}>Lade…</p>}
        {model?.feature_importance?.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 4 }}>WICHTIGSTE FEATURES</div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              {model.feature_importance.slice(0, 7).map((f: any) => (
                <span key={f.feature} className="pill" style={{ background: "var(--panel-2)", color: "var(--text)" }}>
                  {f.feature}: {(f.importance * 100).toFixed(0)}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Ehrliche Edge-Bewertung */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>🔬 Edge-Bewertung — {symbol} (Walk-Forward)</span>
          <button className="secondary" onClick={runEdge} disabled={edgeBusy}>
            {edgeBusy ? "Analysiere…" : "Edge prüfen"}
          </button>
        </h3>
        <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 0 }}>
          Ehrliche, robuste Auswertung: trainiert per Walk-Forward auf der Historie,
          testet gegen Zufall &amp; Buy-and-Hold. Sagt klar, ob ein echter statistischer
          Vorteil messbar ist.
        </p>
        {!edgeEval ? (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>
            {edgeBusy ? "Rechne… (kann ein paar Sekunden dauern)" : "Auf »Edge prüfen« klicken."}
          </p>
        ) : edgeEval.ok === false ? (
          <div className="banner">{edgeEval.error || edgeEval.reason || "Fehler"}</div>
        ) : (
          <>
            <div className="banner" style={
              edgeEval.has_edge
                ? { borderColor: "var(--green)", color: "var(--green)", background: "rgba(46,204,113,.1)" }
                : {}
            }>
              {edgeEval.has_edge ? "✅ " : "❌ "}{edgeEval.verdict} · {edgeEval.n_samples} Samples
            </div>
            <div className="row" style={{ gap: 24, marginTop: 8 }}>
              <div><div style={{ color: "var(--muted)", fontSize: 12 }}>TREFFERQUOTE</div><b>{(edgeEval.significance.hit_rate * 100).toFixed(1)}%</b></div>
              <div><div style={{ color: "var(--muted)", fontSize: 12 }}>SHARPE</div><b>{edgeEval.metrics.sharpe}</b></div>
              <div><div style={{ color: "var(--muted)", fontSize: 12 }}>MAX DD</div><b className="neg">{(edgeEval.metrics.max_drawdown * 100).toFixed(1)}%</b></div>
              <div><div style={{ color: "var(--muted)", fontSize: 12 }}>vs. ZUFALL (p)</div><b>{edgeEval.significance.mc_p_value}</b></div>
              <div><div style={{ color: "var(--muted)", fontSize: 12 }}>BUY&amp;HOLD SHARPE</div><b>{edgeEval.buy_and_hold.sharpe}</b></div>
            </div>
            {edgeEval.feature_importance?.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 4 }}>WICHTIGSTE FEATURES</div>
                <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                  {edgeEval.feature_importance.slice(0, 6).map((f: any) => (
                    <span key={f.feature} className="pill off" style={{ background: "var(--panel-2)", color: "var(--text)" }}>
                      {f.feature}: {(f.importance * 100).toFixed(0)}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div style={{ marginTop: 12 }}>
              <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 4 }}>EMPFEHLUNGEN</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                {edgeEval.recommendations.map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          </>
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
                <tr key={t.id} className={t.status === "OPEN" ? "open" : (t.pnl ?? 0) >= 0 ? "win" : "loss"}>
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
