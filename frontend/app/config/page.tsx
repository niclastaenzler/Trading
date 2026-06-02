"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

const MARKET_LABELS: Record<string, string> = {
  forex: "Forex (Währungen)",
  commodities: "Rohstoffe",
  indices: "Indizes",
  stocks: "Aktien",
};

// Helper to read/write nested config paths immutably.
function setPath(obj: any, path: string, value: any) {
  const keys = path.split(".");
  const clone = structuredClone(obj);
  let cur = clone;
  for (let i = 0; i < keys.length - 1; i++) cur = cur[keys[i]];
  cur[keys[keys.length - 1]] = value;
  return clone;
}

export default function ConfigPage() {
  const router = useRouter();
  const [cfg, setCfg] = useState<any>(null);
  const [universe, setUniverse] = useState<Record<string, string[]>>({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api.getConfig().then((r) => setCfg(r.config));
    api.universe().then((u) => setUniverse(u.groups || {})).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!cfg) return <p>Lädt…</p>;

  const upd = (path: string, value: any) => setCfg(setPath(cfg, path, value));
  const num = (path: string, v: string) => upd(path, parseFloat(v));

  // Add a market group's symbols to the allowed list (unique, keeps existing).
  function addMarket(group: string) {
    const current: string[] = cfg.trading.allowed_symbols || [];
    const merged = Array.from(new Set([...current, ...(universe[group] || [])]));
    upd("trading.allowed_symbols", merged);
    setMsg(`„${MARKET_LABELS[group] || group}" hinzugefügt — unten „Speichern" klicken.`);
  }
  function allMarkets() {
    const merged = Array.from(new Set(Object.values(universe).flat()));
    upd("trading.allowed_symbols", merged);
    setMsg(`Alle Märkte (${merged.length} Instrumente) übernommen — „Speichern" klicken.`);
  }

  async function save() {
    setErr(""); setMsg("");
    try {
      const res: any = await api.updateConfig(cfg);
      setCfg(res.config); // reflect server-side clamping (compliance envelope)
      setMsg("Gespeichert. Die Werte spiegeln die erzwungene Compliance-Hülle wider.");
    } catch (e: any) {
      setErr(e.message);
    }
  }

  // Voreingestellte Trading-Profile. Nach dem Anwenden noch „Speichern" klicken;
  // das Backend klemmt zu riskante Werte über die Compliance-Hülle automatisch.
  const PRESETS: Record<string, any> = {
    Konservativ: {
      "trading.risk_per_trade_pct": 0.5, "trading.max_open_positions": 2,
      "strategy.signal_confidence_threshold": 0.75,
      "automation.manual_confirmation": true, "automation.max_trades_per_hour": 2,
      "automation.max_trades_per_day": 4, "automation.cooldown_seconds": 600,
      "risk.stop_loss_value": 1.5, "risk.take_profit_rr": 2.0,
      "risk.daily_loss_limit_pct": 2.0, "risk.max_drawdown_pct": 8.0,
      "compliance.compliance_mode": true,
    },
    Ausgewogen: {
      "trading.risk_per_trade_pct": 1.0, "trading.max_open_positions": 3,
      "strategy.signal_confidence_threshold": 0.65,
      "automation.manual_confirmation": true, "automation.max_trades_per_hour": 4,
      "automation.max_trades_per_day": 10, "automation.cooldown_seconds": 300,
      "risk.stop_loss_value": 1.5, "risk.take_profit_rr": 2.0,
      "risk.daily_loss_limit_pct": 3.0, "risk.max_drawdown_pct": 10.0,
      "compliance.compliance_mode": true,
    },
    Aggressiv: {
      "trading.risk_per_trade_pct": 1.0, "trading.max_open_positions": 5,
      "strategy.signal_confidence_threshold": 0.6,
      "automation.manual_confirmation": false, "automation.max_trades_per_hour": 6,
      "automation.max_trades_per_day": 20, "automation.cooldown_seconds": 60,
      "risk.stop_loss_value": 1.0, "risk.take_profit_rr": 1.5,
      "risk.daily_loss_limit_pct": 5.0, "risk.max_drawdown_pct": 12.0,
      "compliance.compliance_mode": true,
    },
  };
  function applyPreset(name: string) {
    let next = cfg;
    for (const [path, value] of Object.entries(PRESETS[name])) {
      next = setPath(next, path, value);
    }
    setCfg(next);
    setMsg(`Profil „${name}" übernommen — jetzt unten „Speichern" klicken.`);
  }

  // Small info "ⓘ" with a hover tooltip explaining the field.
  const Info = ({ text }: { text: string }) =>
    text ? (
      <span
        title={text}
        style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 15, height: 15, borderRadius: "50%", fontSize: 10, marginLeft: 6,
          background: "var(--panel-2)", color: "var(--accent)", cursor: "help",
          border: "1px solid var(--border)",
        }}
      >ⓘ</span>
    ) : null;

  const N = (label: string, path: string, step = "any", info = "") => {
    const val = path.split(".").reduce((o, k) => o[k], cfg);
    return (
      <div>
        <label>{label}<Info text={info} /></label>
        <input type="number" step={step} value={val} onChange={(e) => num(path, e.target.value)} />
      </div>
    );
  };
  const B = (label: string, path: string, info = "") => {
    const val = path.split(".").reduce((o, k) => o[k], cfg);
    return (
      <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14 }}>
        <input
          type="checkbox"
          style={{ width: "auto" }}
          checked={!!val}
          onChange={(e) => upd(path, e.target.checked)}
        />
        {label}<Info text={info} />
      </label>
    );
  };

  return (
    <div>
      <h2>Konfiguration</h2>
      {msg && <div className="banner" style={{ borderColor: "var(--green)", color: "var(--green)", background: "rgba(46,204,113,.1)" }}>{msg}</div>}
      {err && <div className="banner">{err}</div>}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>Voreinstellungen (Trading-Profile)</h3>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Schnellstart-Profile. Nach dem Anwenden unten „Speichern" klicken. Zu riskante
          Werte werden durch die Compliance-Hülle automatisch begrenzt.
        </p>
        <div className="row">
          <button className="secondary" onClick={() => applyPreset("Konservativ")}>🛡️ Konservativ</button>
          <button className="secondary" onClick={() => applyPreset("Ausgewogen")}>⚖️ Ausgewogen</button>
          <button className="secondary" onClick={() => applyPreset("Aggressiv")}>🔥 Aggressiv</button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>Märkte / Portfolio</h3>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Wähle, welche Märkte gehandelt werden. Die KI scannt dann alle Instrumente
          und entscheidet, was gehandelt wird. Aktuell:{" "}
          <b>{(cfg.trading.allowed_symbols || []).length}</b> Instrumente.
        </p>
        <div className="row">
          {Object.keys(universe).map((g) => (
            <button key={g} className="secondary" onClick={() => addMarket(g)}>
              + {MARKET_LABELS[g] || g} ({universe[g].length})
            </button>
          ))}
          <button onClick={allMarkets}>🌍 Alle Märkte</button>
          <button className="secondary" onClick={() => upd("trading.allowed_symbols", [])}>Leeren</button>
        </div>
        <p style={{ color: "var(--muted)", fontSize: 12, marginTop: 12, wordBreak: "break-word" }}>
          {(cfg.trading.allowed_symbols || []).join(", ") || "— keine —"}
        </p>
      </div>

      <fieldset className="fieldset">
        <legend>Trading</legend>
        <div className="grid">
          {N("Risiko pro Trade (%)", "trading.risk_per_trade_pct", "any",
            "Wie viel % deines Kontos pro Trade riskiert wird (Verlust bis zum Stop-Loss). Konservativ: 0,5–1 %.")}
          {N("Max. offene Positionen", "trading.max_open_positions", "1",
            "Wie viele Positionen gleichzeitig offen sein dürfen. Begrenzt das Gesamtrisiko.")}
          <div>
            <label>Erlaubte Symbole (durch Komma getrennt)</label>
            <input
              value={(cfg.trading.allowed_symbols || []).join(",")}
              onChange={(e) => upd("trading.allowed_symbols", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
            />
          </div>
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14 }}>
          <input
            type="checkbox"
            style={{ width: "auto" }}
            checked={(cfg.trading.session_windows_utc || []).length === 0}
            onChange={(e) =>
              upd("trading.session_windows_utc", e.target.checked ? [] : [["07:00", "16:00"]])
            }
          />
          Rund um die Uhr handeln (kein Zeitfenster)
        </label>
        <p style={{ color: "var(--muted)", fontSize: 12 }}>
          Aktiv: {(cfg.trading.session_windows_utc || []).length === 0
            ? "immer (24/7)"
            : (cfg.trading.session_windows_utc || []).map((w: string[]) => `${w[0]}–${w[1]} UTC`).join(", ")}
        </p>
      </fieldset>

      <fieldset className="fieldset">
        <legend>Strategie</legend>
        {B("KI-Modell aktiv", "strategy.ai_model_enabled",
          "Nutzt das trainierte ML-Modell (sonst nur Indikatoren/Muster).")}
        {B("Mustererkennung aktiv", "strategy.pattern_recognition_enabled",
          "Erkennt Candlestick-Muster & Ausbrüche als zusätzliches Signal.")}
        {B("Trendfilter aktiv", "strategy.trend_filter_enabled",
          "Handelt nur in Trendrichtung (kein Gegen-den-Trend-Handel).")}
        {B("News-/Sentiment-Overlay (Platzhalter)", "strategy.use_sentiment",
          "Vorbereitet, aber inaktiv bis eine echte News-Datenquelle angebunden ist — wirkt aktuell neutral.")}
        <div className="grid">
          {N("Signal-Konfidenzschwelle", "strategy.signal_confidence_threshold", "any",
            "Mindest-Konfidenz (0,5–0,99), bevor überhaupt gehandelt wird. Höher = weniger, aber sicherere Trades.")}
          {N("RSI-Länge", "strategy.indicators.rsi_length", "1")}
          {N("MACD schnell", "strategy.indicators.macd_fast", "1")}
          {N("MACD langsam", "strategy.indicators.macd_slow", "1")}
          {N("MACD Signal", "strategy.indicators.macd_signal", "1")}
          {N("EMA schnell", "strategy.indicators.ema_fast", "1")}
          {N("EMA langsam", "strategy.indicators.ema_slow", "1")}
          {N("ATR-Länge", "strategy.indicators.atr_length", "1")}
        </div>
      </fieldset>

      <fieldset className="fieldset">
        <legend>Automatisierung</legend>
        {B("Manuelle Bestätigung (Halb-Automatik)", "automation.manual_confirmation")}
        <div className="grid">
          {N("Max. Trades / Stunde", "automation.max_trades_per_hour", "1")}
          {N("Max. Trades / Tag", "automation.max_trades_per_day", "1")}
          {N("Abkühlzeit zwischen Trades (s)", "automation.cooldown_seconds", "1")}
        </div>
      </fieldset>

      <fieldset className="fieldset">
        <legend>Risikomanagement</legend>
        <div className="grid">
          <div>
            <label>Stop-Loss-Typ</label>
            <select value={cfg.risk.stop_loss_type} onChange={(e) => upd("risk.stop_loss_type", e.target.value)}>
              <option value="atr">ATR-Vielfaches</option>
              <option value="percent">Prozent</option>
            </select>
          </div>
          {N("Stop-Loss-Wert", "risk.stop_loss_value", "any",
            "Abstand des Stops: bei ATR = Vielfaches der Schwankung, bei Prozent = % vom Preis.")}
          {N("Take-Profit (Chance:Risiko)", "risk.take_profit_rr", "any",
            "Gewinnziel relativ zum Risiko. 2,0 = Ziel ist doppelt so weit wie der Stop.")}
          {N("Tagesverlust-Limit (%)", "risk.daily_loss_limit_pct", "any",
            "Maximaler Verlust pro Tag in % — danach stoppt der Handel automatisch.")}
          {N("Max. Drawdown (%)", "risk.max_drawdown_pct", "any",
            "Maximaler Rückgang vom Höchststand, bevor der Handel pausiert.")}
        </div>
        {B("Trailing-Stop aktiv", "risk.trailing_stop_enabled",
          "Zieht den Stop bei Gewinn nach.")}
        {B("Positionsgröße nach KI-Konfidenz skalieren", "risk.confidence_scaled_sizing",
          "Stärkere Signale bekommen größere Positionen (innerhalb des Risiko-Budgets).")}
      </fieldset>

      <fieldset className="fieldset">
        <legend>Edge-Layer (selektives Handeln)</legend>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Nur die wirklich attraktiven Setups handeln — Ziel ist besseres, nicht mehr Trading.
        </p>
        {B("Edge-Layer aktiv", "edge.enabled",
          "Filtert schwache Setups heraus — handelt nur, wenn der Kontext stimmt.")}
        {B("Nur im Trend handeln (Seitwärtsphasen meiden)", "edge.require_trend_regime",
          "Überspringt choppy/seitwärts laufende Märkte (oft Verlustquelle).")}
        <div className="grid">
          {N("Mindest-Edge-Score (0–1)", "edge.min_edge_score", "any",
            "Gesamtnote aus Konfidenz + Kontext. Höher = selektiver. Empf.: 0,5.")}
          {N("Mindest-Trendstärke (0–1)", "edge.min_trend_strength", "any",
            "Wie klar der Trend sein muss (Efficiency Ratio). 0,3 = moderater Trend.")}
          {N("Max. Volatilitäts-Perzentil (0–1)", "edge.max_volatility_percentile", "any",
            "Überspringt extrem volatile Phasen. 0,9 = nur die obersten 10 % meiden.")}
        </div>
      </fieldset>

      <fieldset className="fieldset">
        <legend>Compliance</legend>
        {B("Compliance-Modus (erzwingt konservative Obergrenzen)", "compliance.compliance_mode")}
        {B("Bei hoher Volatilität pausieren", "compliance.halt_on_high_volatility")}
        <div className="grid">
          {N("Max. API-Anfragen / Minute", "compliance.max_api_requests_per_minute", "1")}
          {N("Min. Sekunden zwischen Trades", "compliance.min_seconds_between_trades", "1")}
          {N("Volatilitäts-Schwelle (ATR/Preis)", "compliance.high_volatility_atr_ratio")}
          <div>
            <label>Protokoll-Stufe</label>
            <select value={cfg.compliance.logging_level} onChange={(e) => upd("compliance.logging_level", e.target.value)}>
              <option value="full_audit">Vollständiges Audit</option>
              <option value="basic">Basis</option>
            </select>
          </div>
        </div>
      </fieldset>

      <button onClick={save}>Konfiguration speichern</button>
    </div>
  );
}
