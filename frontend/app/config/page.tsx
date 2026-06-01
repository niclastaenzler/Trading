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
      setMsg("Saved. Values reflect the enforced compliance envelope.");
    } catch (e: any) {
      setErr(e.message);
    }
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
      <h2>Configuration</h2>
      {msg && <div className="banner" style={{ borderColor: "var(--green)", color: "var(--green)", background: "rgba(46,204,113,.1)" }}>{msg}</div>}
      {err && <div className="banner">{err}</div>}

      <fieldset className="fieldset">
        <legend>Trading</legend>
        <div className="grid">
          {N("Risk per trade (%)", "trading.risk_per_trade_pct")}
          {N("Max open positions", "trading.max_open_positions", "1")}
          <div>
            <label>Allowed symbols (comma separated)</label>
            <input
              value={(cfg.trading.allowed_symbols || []).join(",")}
              onChange={(e) => upd("trading.allowed_symbols", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
            />
          </div>
        </div>
      </fieldset>

      <fieldset className="fieldset">
        <legend>Strategy</legend>
        {B("AI model enabled", "strategy.ai_model_enabled")}
        {B("Pattern recognition enabled", "strategy.pattern_recognition_enabled")}
        {B("Trend filter enabled", "strategy.trend_filter_enabled")}
        <div className="grid">
          {N("Signal confidence threshold", "strategy.signal_confidence_threshold")}
          {N("RSI length", "strategy.indicators.rsi_length", "1")}
          {N("MACD fast", "strategy.indicators.macd_fast", "1")}
          {N("MACD slow", "strategy.indicators.macd_slow", "1")}
          {N("MACD signal", "strategy.indicators.macd_signal", "1")}
          {N("EMA fast", "strategy.indicators.ema_fast", "1")}
          {N("EMA slow", "strategy.indicators.ema_slow", "1")}
          {N("ATR length", "strategy.indicators.atr_length", "1")}
        </div>
      </fieldset>

      <fieldset className="fieldset">
        <legend>Automation</legend>
        {B("Manual confirmation (semi-auto)", "automation.manual_confirmation")}
        <div className="grid">
          {N("Max trades / hour", "automation.max_trades_per_hour", "1")}
          {N("Max trades / day", "automation.max_trades_per_day", "1")}
          {N("Cooldown between trades (s)", "automation.cooldown_seconds", "1")}
        </div>
      </fieldset>

      <fieldset className="fieldset">
        <legend>Risk management</legend>
        <div className="grid">
          <div>
            <label>Stop-loss type</label>
            <select value={cfg.risk.stop_loss_type} onChange={(e) => upd("risk.stop_loss_type", e.target.value)}>
              <option value="atr">ATR multiple</option>
              <option value="percent">Percent</option>
            </select>
          </div>
          {N("Stop-loss value", "risk.stop_loss_value")}
          {N("Take-profit (R:R)", "risk.take_profit_rr")}
          {N("Daily loss limit (%)", "risk.daily_loss_limit_pct")}
          {N("Max drawdown (%)", "risk.max_drawdown_pct")}
        </div>
        {B("Trailing stop enabled", "risk.trailing_stop_enabled")}
      </fieldset>

      <fieldset className="fieldset">
        <legend>Compliance</legend>
        {B("Compliance mode (enforces conservative ceilings)", "compliance.compliance_mode")}
        {B("Halt on high volatility", "compliance.halt_on_high_volatility")}
        <div className="grid">
          {N("Max API requests / minute", "compliance.max_api_requests_per_minute", "1")}
          {N("Min seconds between trades", "compliance.min_seconds_between_trades", "1")}
          {N("High-volatility ATR ratio", "compliance.high_volatility_atr_ratio")}
          <div>
            <label>Logging level</label>
            <select value={cfg.compliance.logging_level} onChange={(e) => upd("compliance.logging_level", e.target.value)}>
              <option value="full_audit">Full audit</option>
              <option value="basic">Basic</option>
            </select>
          </div>
        </div>
      </fieldset>

      <button onClick={save}>Save configuration</button>
    </div>
  );
}
