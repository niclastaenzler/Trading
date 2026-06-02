"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

const EquityChart = dynamic(() => import("@/app/components/EquityChart"), { ssr: false });

// Each "edge" maps to a config flag, with a plain explanation + how the AI uses it.
const EDGES: { path: string; title: string; desc: string; learn: string }[] = [
  {
    path: "strategy.ai_model_enabled",
    title: "🧠 KI-Modell (Machine Learning)",
    desc: "Ein auf historischen Daten trainiertes Modell, das eine Wahrscheinlichkeit (Konfidenz) für die nächste Kursrichtung liefert.",
    learn: "Lernt aus den Features (Returns, Volatilität, Momentum, Trend, Regime …) per Walk-Forward. Die Feature-Importance unten zeigt, welche Edges das Modell aktuell am stärksten gewichtet.",
  },
  {
    path: "strategy.pattern_recognition_enabled",
    title: "📊 Mustererkennung",
    desc: "Candlestick-Muster (Hammer, Engulfing …) und Ausbrüche über Unterstützung/Widerstand.",
    learn: "Regelbasiert. Fließt als gewichtete Stimme in die Signalfusion ein; die KI kann das Zusammenspiel mitbewerten.",
  },
  {
    path: "strategy.trend_filter_enabled",
    title: "📈 Trendfilter",
    desc: "Handelt nur in Richtung des übergeordneten Trends (EMA-Ausrichtung).",
    learn: "Harter Filter gegen Trades gegen den Trend — reduziert Fehlsignale in klaren Trends.",
  },
  {
    path: "edge.enabled",
    title: "🎯 Edge-Layer (selektives Handeln)",
    desc: "Lässt nur Setups durch, deren Gesamt-Edge-Score hoch genug ist. Ziel: besser statt mehr handeln.",
    learn: "Kombiniert Konfidenz + Marktkontext zu einem Score und sortiert damit die besten Chancen nach oben.",
  },
  {
    path: "edge.require_trend_regime",
    title: "🌊 Regime-Filter (nur im Trend)",
    desc: "Überspringt Seitwärts-/choppy Märkte (oft Verlustquelle) anhand der Trendstärke.",
    learn: "Erkennt das Marktregime (Trend vs. Seitwärts) über die Efficiency Ratio und handelt nur im Trend.",
  },
  {
    path: "strategy.use_sentiment",
    title: "📰 News-Sentiment-Overlay",
    desc: "Bezieht Nachrichten-Stimmung (Alpha Vantage) ein und blockt Trades gegen klar negative/positive News.",
    learn: "Aktiv nur mit API-Key (sonst neutral). Wirkt als zusätzlicher Filter/Tilt auf den Edge-Score.",
  },
  {
    path: "risk.confidence_scaled_sizing",
    title: "⚖️ Konfidenz-Positionsgröße",
    desc: "Stärkere Signale bekommen größere Positionen — innerhalb des Risiko-Budgets.",
    learn: "Übersetzt die Modell-Konfidenz direkt in die Positionsgröße (mehr Überzeugung = mehr Einsatz).",
  },
];

function getPath(obj: any, path: string) {
  return path.split(".").reduce((o, k) => (o ? o[k] : undefined), obj);
}
function setPath(obj: any, path: string, value: any) {
  const keys = path.split(".");
  const clone = structuredClone(obj);
  let cur = clone;
  for (let i = 0; i < keys.length - 1; i++) cur = cur[keys[i]];
  cur[keys[keys.length - 1]] = value;
  return clone;
}

export default function EdgesPage() {
  const router = useRouter();
  const [cfg, setCfg] = useState<any>(null);
  const [model, setModel] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [symbol, setSymbol] = useState("EURUSD");
  const [bars, setBars] = useState(500);
  const [bt, setBt] = useState<any>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api.getConfig().then((r) => setCfg(r.config));
    api.modelStatus().then(setModel).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!cfg) return <p>Lädt…</p>;

  const toggle = (path: string) => setCfg(setPath(cfg, path, !getPath(cfg, path)));

  async function save() {
    setBusy(true); setMsg("");
    try { await api.updateConfig(cfg); setMsg("Edges gespeichert."); }
    catch (e: any) { setMsg("Fehler: " + e.message); }
    setBusy(false);
  }
  async function runBacktest() {
    setBusy(true); setBt(null);
    try { setBt(await api.backtest(symbol, bars)); }
    catch (e: any) { setMsg("Backtest-Fehler: " + e.message); }
    setBusy(false);
  }
  async function train() {
    setBusy(true); setMsg("");
    try { await api.trainModel(); setModel(await api.modelStatus()); setMsg("Modell trainiert."); }
    catch (e: any) { setMsg("Training-Fehler: " + e.message); }
    setBusy(false);
  }

  const activeCount = EDGES.filter((e) => getPath(cfg, e.path)).length;

  return (
    <div>
      <h2>Edges</h2>
      <p style={{ color: "var(--muted)", fontSize: 14 }}>
        „Edges" sind die Bausteine, aus denen Signale und Entscheidungen entstehen.
        Schalte sie ein/aus und teste die Wirkung per Backtest. Aktiv: <b>{activeCount}/{EDGES.length}</b>.
      </p>
      {msg && <div className="banner" style={{ borderColor: "var(--green)", color: "var(--green)", background: "rgba(46,204,113,.1)" }}>{msg}</div>}

      {/* Was die KI gelernt hat */}
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 className="row" style={{ justifyContent: "space-between" }}>
          <span>Was die KI aus den Edges gelernt hat</span>
          <button className="secondary" onClick={train} disabled={busy}>{busy ? "…" : "Modell trainieren"}</button>
        </h3>
        {model?.is_trained ? (
          <>
            <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
              Out-of-Sample-Genauigkeit: <b>{model.metrics?.test_score != null ? (model.metrics.test_score * 100).toFixed(1) + "%" : "—"}</b>
              {" "}· trainiert auf <b>{model.metrics?.instruments ?? "—"}</b> Instrumenten.
              Wichtigste Features (= worauf die KI achtet):
            </p>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              {(model.feature_importance || []).slice(0, 8).map((f: any) => (
                <span key={f.feature} className="pill" style={{ background: "var(--panel-2)", color: "var(--text)" }}>
                  {f.feature}: {(f.importance * 100).toFixed(0)}
                </span>
              ))}
            </div>
          </>
        ) : (
          <p style={{ color: "var(--muted)", fontSize: 13 }}>
            Noch kein trainiertes Modell — auf „Modell trainieren" klicken (nutzt deine Märkte).
            Bis dahin rechnet die Engine mit der transparenten Heuristik.
          </p>
        )}
      </div>

      {/* Edge-Liste */}
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        {EDGES.map((e) => {
          const on = !!getPath(cfg, e.path);
          return (
            <div className="card" key={e.path} style={on ? { borderColor: "var(--accent)" } : {}}>
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <h3 style={{ margin: 0, textTransform: "none", color: "var(--text)", fontSize: 15 }}>{e.title}</h3>
                <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input type="checkbox" style={{ width: "auto" }} checked={on} onChange={() => toggle(e.path)} />
                  <span className={`pill ${on ? "on" : "off"}`}>{on ? "AN" : "AUS"}</span>
                </label>
              </div>
              <p style={{ fontSize: 13, margin: "8px 0" }}>{e.desc}</p>
              <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}><b>Wie die KI es nutzt:</b> {e.learn}</p>
            </div>
          );
        })}
      </div>

      <div className="row" style={{ marginTop: 16 }}>
        <button onClick={save} disabled={busy}>Edges speichern</button>
      </div>

      {/* Backtest mit aktuellen Edges */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Backtest mit aktuellen Edges</h3>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Testet die aktuell aktiven Edges auf Verlauf — erst <b>speichern</b>, dann testen.
        </p>
        <div className="row">
          <div><label>Symbol</label><input value={symbol} onChange={(e) => setSymbol(e.target.value)} /></div>
          <div><label>Kerzen</label><input type="number" value={bars} onChange={(e) => setBars(parseInt(e.target.value))} /></div>
          <button className="secondary" style={{ alignSelf: "flex-end" }} onClick={runBacktest} disabled={busy}>
            {busy ? "Läuft…" : "Backtest starten"}
          </button>
        </div>
        {bt && (
          <>
            <div className="grid" style={{ marginTop: 16 }}>
              <div className="card"><h3>Rendite</h3><div className={`metric ${bt.total_return_pct >= 0 ? "pos" : "neg"}`}>{bt.total_return_pct}%</div></div>
              <div className="card"><h3>Trades</h3><div className="metric">{bt.num_trades}</div></div>
              <div className="card"><h3>Trefferquote</h3><div className="metric">{(bt.win_rate * 100).toFixed(1)}%</div></div>
              <div className="card"><h3>Sharpe</h3><div className="metric">{bt.sharpe}</div></div>
              <div className="card"><h3>Max. DD</h3><div className="metric neg">{bt.max_drawdown_pct}%</div></div>
              <div className="card"><h3>Profit-Faktor</h3><div className="metric">{bt.profit_factor}</div></div>
            </div>
            <div className="card" style={{ marginTop: 16 }}>
              <h3>Equity-Kurve</h3>
              <EquityChart data={bt.equity_curve} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
