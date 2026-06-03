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

// Small info "ⓘ" with a hover tooltip explaining the field.
function InfoDot({ text }: { text: string }) {
  if (!text) return null;
  return (
    <span
      title={text}
      style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 15, height: 15, borderRadius: "50%", fontSize: 10, marginLeft: 6,
        background: "var(--panel-2)", color: "var(--accent)", cursor: "help",
        border: "1px solid var(--border)",
      }}
    >ⓘ</span>
  );
}

// Editable number field with a LOCAL string buffer, so you can type decimals
// (e.g. "2.5") and temporarily clear the field without it snapping back or
// producing NaN. The parsed number is committed to the config only when valid.
function NumField({
  label, value, step = "any", info = "", onCommit,
}: {
  label: string; value: number; step?: string; info?: string;
  onCommit: (n: number) => void;
}) {
  const initial = value === undefined || value === null || Number.isNaN(value)
    ? "" : String(value);
  const [raw, setRaw] = useState<string>(initial);
  // Sync when the value changes from outside (e.g. preset applied, save clamp).
  useEffect(() => {
    setRaw(value === undefined || value === null || Number.isNaN(value) ? "" : String(value));
  }, [value]);
  return (
    <div>
      <label>{label}<InfoDot text={info} /></label>
      <input
        type="number"
        step={step}
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          const n = parseFloat(e.target.value);
          if (!Number.isNaN(n)) onCommit(n);
        }}
      />
    </div>
  );
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
      setCfg(res.config); // reflect server-side normalisation (e.g. cooldown floor)
      setMsg("Gespeichert ✓ Deine Einstellungen sind aktiv.");
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function resetAccount() {
    if (!window.confirm(
      "Wirklich ALLES zurücksetzen?\n\n• Trade-Verlauf wird gelöscht\n• Kontostand & Höchststand zurückgesetzt\n• Tagesverlust = 0, Not-Aus aufgehoben\n\nDeine Einstellungen (Risiko, Märkte …) bleiben erhalten."
    )) return;
    setErr(""); setMsg("");
    try {
      const res: any = await api.resetAccount();
      const r: any = await api.getConfig();
      setCfg(r.config);
      setMsg(res.message || "Konto zurückgesetzt.");
    } catch (e: any) {
      setErr(e.message);
    }
  }

  // Voreingestellte Trading-Profile als Startpunkte. Nach dem Anwenden noch
  // „Speichern" klicken. Werte sind frei wählbar — der Risiko-Check zeigt die Folgen.
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
      "trading.risk_per_trade_pct": 2.0, "trading.max_open_positions": 10,
      "strategy.signal_confidence_threshold": 0.58,
      "automation.manual_confirmation": false, "automation.max_trades_per_hour": 15,
      "automation.max_trades_per_day": 60, "automation.cooldown_seconds": 30,
      "risk.stop_loss_value": 1.0, "risk.take_profit_rr": 1.5,
      "risk.daily_loss_limit_pct": 10.0, "risk.max_drawdown_pct": 20.0,
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

  const N = (label: string, path: string, step = "any", info = "") => {
    const val = path.split(".").reduce((o, k) => o?.[k], cfg);
    return (
      <NumField
        key={path}
        label={label}
        value={val}
        step={step}
        info={info}
        onCommit={(n) => upd(path, n)}
      />
    );
  };
  const B = (label: string, path: string, info = "") => {
    const val = path.split(".").reduce((o, k) => o?.[k], cfg);
    return (
      <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14 }}>
        <input
          type="checkbox"
          style={{ width: "auto" }}
          checked={!!val}
          onChange={(e) => upd(path, e.target.checked)}
        />
        {label}<InfoDot text={info} />
      </label>
    );
  };

  // Live-Risiko-Check: übersetzt die Zahlen in Klartext. Ersetzt die früheren
  // Hard-Caps durch eine informierte Entscheidung — der Worst-Case ist, dass alle
  // offenen Positionen gleichzeitig ihren Stop-Loss auslösen.
  const riskPerTrade = Number(cfg.trading.risk_per_trade_pct) || 0;
  const maxOpen = Number(cfg.trading.max_open_positions) || 0;
  const worstCase = riskPerTrade * maxOpen; // % vom Konto, wenn alle Stops fallen
  const auto = !cfg.automation.manual_confirmation;
  const around = (cfg.trading.session_windows_utc || []).length === 0;
  const dailyOn = cfg.risk.daily_loss_limit_enabled !== false;
  const risk =
    worstCase <= 5
      ? { color: "var(--green)", bg: "rgba(46,204,113,.10)", label: "Konservativ", icon: "🛡️" }
      : worstCase <= 15
      ? { color: "#d4a72c", bg: "rgba(212,167,44,.12)", label: "Ausgewogen", icon: "⚖️" }
      : worstCase <= 40
      ? { color: "#e67e22", bg: "rgba(230,126,34,.12)", label: "Aggressiv", icon: "🔥" }
      : { color: "var(--red, #e74c3c)", bg: "rgba(231,76,60,.12)", label: "Sehr riskant", icon: "⚠️" };

  return (
    <div>
      <h2>Konfiguration</h2>
      {msg && <div className="banner" style={{ borderColor: "var(--green)", color: "var(--green)", background: "rgba(46,204,113,.1)" }}>{msg}</div>}
      {err && <div className="banner">{err}</div>}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>Voreinstellungen (Trading-Profile)</h3>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Schnellstart-Profile. Nach dem Anwenden unten „Speichern" klicken. Du kannst
          danach jeden Wert frei anpassen — der Risiko-Check unten zeigt dir, was deine
          Einstellung bedeutet.
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
        <button onClick={save} style={{ marginTop: 4 }}>💾 Märkte speichern</button>
      </div>

      {/* ───────── Einfach: nur das Wichtigste ───────── */}
      <fieldset className="fieldset">
        <legend>Einstellungen</legend>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Tipp: Wähle oben einfach ein Profil — dann passt alles automatisch. Hier kannst
          du die wichtigsten Werte noch von Hand anpassen.
        </p>
        <div className="grid">
          {N("Risiko pro Trade (%)", "trading.risk_per_trade_pct", "any",
            "Wie viel % deines Kontos pro Trade eingesetzt wird. Höher = größere Gewinne UND Verluste.")}
          {N("Max. gleichzeitige Trades", "trading.max_open_positions", "1",
            "Wie viele Positionen gleichzeitig offen sein dürfen.")}
          {dailyOn && N("Tagesverlust-Limit (%)", "risk.daily_loss_limit_pct", "any",
            "Verlierst du an einem Tag so viele %, stoppt der Handel automatisch für den Tag.")}
        </div>
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14 }}>
          <input
            type="checkbox"
            style={{ width: "auto" }}
            checked={dailyOn}
            onChange={(e) => upd("risk.daily_loss_limit_enabled", e.target.checked)}
          />
          Handel bei Tagesverlust automatisch stoppen
          <InfoDot text="Aus = der Bot handelt weiter, egal wie viel an einem Tag verloren wird. Dann gibt es keine Tagesbremse mehr." />
        </label>
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 14 }}>
          <input
            type="checkbox"
            style={{ width: "auto" }}
            checked={!cfg.automation.manual_confirmation}
            onChange={(e) => upd("automation.manual_confirmation", !e.target.checked)}
          />
          Vollautomatisch handeln (du musst keinen Trade einzeln bestätigen)
        </label>
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

        {/* Live-Risiko-Check — Klartext statt Hard-Caps */}
        <div
          style={{
            marginTop: 18, padding: "12px 14px", borderRadius: 10,
            border: `1px solid ${risk.color}`, background: risk.bg,
          }}
        >
          <div style={{ fontWeight: 600, color: risk.color, marginBottom: 6 }}>
            {risk.icon} Risiko-Check: {risk.label}
          </div>
          <div style={{ fontSize: 13, lineHeight: 1.55 }}>
            Du riskierst <b>{riskPerTrade}%</b> pro Trade bei bis zu <b>{maxOpen}</b>{" "}
            gleichzeitigen Positionen. Im schlimmsten Fall (alle Stops fallen auf einmal)
            wären das <b>≈ {worstCase.toFixed(1)}%</b> deines Kontos auf einmal.
            {worstCase > 40 && (
              <> <b style={{ color: risk.color }}>Das ist sehr viel</b> — auf echtem Geld
              könntest du damit einen großen Teil des Kontos an einem schlechten Tag verlieren.</>
            )}
            <br />
            {dailyOn ? (
              <>Der Handel stoppt automatisch, sobald dein Tagesverlust{" "}
              <b>{Number(cfg.risk.daily_loss_limit_pct) || 0}%</b> erreicht.{" "}</>
            ) : (
              <><b style={{ color: "var(--red, #e74c3c)" }}>Keine Tagesbremse</b> — der Bot
              handelt weiter, egal wie viel an einem Tag verloren wird.{" "}</>
            )}
            {auto ? "Trades laufen vollautomatisch." : "Du bestätigst jeden Trade selbst."}{" "}
            {around ? "Gehandelt wird rund um die Uhr." : "Gehandelt wird nur im Zeitfenster."}
          </div>
        </div>

        <button onClick={save} style={{ marginTop: 16 }}>💾 Speichern</button>
      </fieldset>

      {/* ───────── Erweitert: eingeklappt, optional ───────── */}
      <details className="card" style={{ marginTop: 16 }}>
        <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 15 }}>
          ⚙️ Erweiterte Einstellungen (optional — kannst du ignorieren)
        </summary>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>
          Nur ändern, wenn du genau weißt, was du tust. Sonst reichen Profil + die
          Werte oben völlig aus.
        </p>

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
          <legend>Trade-Häufigkeit</legend>
          <div className="grid">
            {N("Max. Trades / Stunde", "automation.max_trades_per_hour", "1",
              "Obergrenze pro Stunde. Hoch = mehr Trades möglich.")}
            {N("Max. Trades / Tag", "automation.max_trades_per_day", "1")}
            {N("Abkühlzeit zwischen Trades (s)", "automation.cooldown_seconds", "1",
              "Mindestpause pro Symbol zwischen zwei Trades.")}
          </div>
        </fieldset>

        <fieldset className="fieldset">
          <legend>Stop-Loss & Take-Profit</legend>
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
            {N("Max. Drawdown (%)", "risk.max_drawdown_pct", "any",
              "Maximaler Rückgang vom Höchststand, bevor der Handel pausiert.")}
          </div>
          {B("Drawdown-Schutz aktiv (Stopp bei Rückgang vom Höchststand)", "risk.max_drawdown_enabled",
            "Achtung: misst vom Allzeit-Höchststand. Aus = dieser zweite Stopp ist deaktiviert — oft die eigentliche Ursache, wenn der Bot 'einfach nicht mehr handelt'.")}
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
          <legend>Compliance / Sicherheit</legend>
          {B("Compliance-Modus", "compliance.compliance_mode",
            "Erzwingt den Pflicht-Stop-Loss. Limits steuerst du selbst.")}
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

        <button onClick={save}>💾 Erweiterte Einstellungen speichern</button>
      </details>

      {/* ───────── Danger Zone: kompletter Neustart ───────── */}
      <div
        className="card"
        style={{ marginTop: 16, border: "1px solid var(--red, #e74c3c)" }}
      >
        <h3 style={{ color: "var(--red, #e74c3c)", marginTop: 0 }}>🧹 Alles zurücksetzen</h3>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 0 }}>
          Sauberer Neustart, wenn der Bot wegen Tagesverlust oder Drawdown „klemmt":
          löscht den <b>Trade-Verlauf</b>, setzt <b>Kontostand</b> &amp; <b>Höchststand</b>{" "}
          zurück (→ Tagesverlust = 0), und hebt den <b>Not-Aus</b> auf. Deine
          Einstellungen (Risiko, Märkte, Profile) bleiben erhalten. Auto-Handel wird
          danach auf AUS gesetzt — du schaltest ihn bewusst wieder ein.
        </p>
        <button className="danger" onClick={resetAccount}>🧹 Konto &amp; Verlauf zurücksetzen</button>
      </div>
    </div>
  );
}
