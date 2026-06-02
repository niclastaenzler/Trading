"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

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
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api.getConfig().then((r) => setCfg(r.config));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!cfg) return <p>Loading…</p>;

  const upd = (path: string, value: any) => setCfg(setPath(cfg, path, value));
  const num = (path: string, v: string) => upd(path, parseFloat(v));

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

  const N = (label: string, path: string, step = "any") => {
    const val = path.split(".").reduce((o, k) => o[k], cfg);
    return (
      <div>
        <label>{label}</label>
        <input type="number" step={step} value={val} onChange={(e) => num(path, e.target.value)} />
      </div>
    );
  };
  const B = (label: string, path: string) => {
    const val = path.split(".").reduce((o, k) => o[k], cfg);
    return (
      <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14 }}>
        <input
          type="checkbox"
          style={{ width: "auto" }}
          checked={!!val}
          onChange={(e) => upd(path, e.target.checked)}
        />
        {label}
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

      <fieldset className="fieldset">
        <legend>Trading</legend>
        <div className="grid">
          {N("Risiko pro Trade (%)", "trading.risk_per_trade_pct")}
          {N("Max. offene Positionen", "trading.max_open_positions", "1")}
          <div>
            <label>Erlaubte Symbole (durch Komma getrennt)</label>
            <input
              value={(cfg.trading.allowed_symbols || []).join(",")}
              onChange={(e) => upd("trading.allowed_symbols", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
            />
          </div>
        </div>
      </fieldset>

      <fieldset className="fieldset">
        <legend>Strategie</legend>
        {B("KI-Modell aktiv", "strategy.ai_model_enabled")}
        {B("Mustererkennung aktiv", "strategy.pattern_recognition_enabled")}
        {B("Trendfilter aktiv", "strategy.trend_filter_enabled")}
        <div className="grid">
          {N("Signal-Konfidenzschwelle", "strategy.signal_confidence_threshold")}
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
          {N("Stop-Loss-Wert", "risk.stop_loss_value")}
          {N("Take-Profit (Chance:Risiko)", "risk.take_profit_rr")}
          {N("Tagesverlust-Limit (%)", "risk.daily_loss_limit_pct")}
          {N("Max. Drawdown (%)", "risk.max_drawdown_pct")}
        </div>
        {B("Trailing-Stop aktiv", "risk.trailing_stop_enabled")}
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
