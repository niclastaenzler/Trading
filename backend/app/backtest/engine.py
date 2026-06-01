"""Event-driven backtesting engine.

Walks an OHLCV history bar by bar, reusing the SAME signal + risk logic as live
trading so results are representative. One position at a time per symbol (simple
MVP); stop-loss / take-profit are evaluated intrabar using the bar's range.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.services.config_defaults import TradingConfigModel
from app.services.risk_manager import RiskManager
from app.services.signal_engine import generate_signal


@dataclass
class BacktestResult:
    starting_equity: float
    ending_equity: float
    total_return_pct: float
    num_trades: int
    win_rate: float
    max_drawdown_pct: float
    sharpe: float
    equity_curve: list[float] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)


def run_backtest(
    symbol: str,
    ohlcv: pd.DataFrame,
    config: TradingConfigModel,
    starting_equity: float = 10_000.0,
    warmup: int = 60,
) -> BacktestResult:
    risk = RiskManager(config)
    equity = starting_equity
    peak = equity
    equity_curve: list[float] = []
    trades: list[dict] = []
    position: dict | None = None

    for i in range(warmup, len(ohlcv)):
        window = ohlcv.iloc[: i + 1]
        bar = ohlcv.iloc[i]

        # Manage an open position first (check stop / target against this bar).
        if position is not None:
            exit_price = None
            if position["side"] == "BUY":
                if bar["low"] <= position["stop_loss"]:
                    exit_price = position["stop_loss"]
                elif bar["high"] >= position["take_profit"]:
                    exit_price = position["take_profit"]
            else:
                if bar["high"] >= position["stop_loss"]:
                    exit_price = position["stop_loss"]
                elif bar["low"] <= position["take_profit"]:
                    exit_price = position["take_profit"]

            if exit_price is not None:
                direction = 1 if position["side"] == "BUY" else -1
                pnl = (exit_price - position["entry_price"]) * position["quantity"] * direction
                equity += pnl
                trades.append(
                    {
                        "side": position["side"],
                        "entry": position["entry_price"],
                        "exit": exit_price,
                        "pnl": round(pnl, 2),
                    }
                )
                position = None

        # Look for a new entry only when flat.
        if position is None:
            signal = generate_signal(symbol, window, config.strategy)
            if signal.actionable:
                plan = risk.build_plan(signal, equity)
                verdict = risk.validate(
                    plan, open_positions=0, equity=equity,
                    realized_pnl_today=0.0, peak_equity=peak,
                )
                if verdict.ok:
                    position = {
                        "side": plan.side, "entry_price": plan.entry_price,
                        "stop_loss": plan.stop_loss, "take_profit": plan.take_profit,
                        "quantity": plan.quantity,
                    }

        peak = max(peak, equity)
        equity_curve.append(round(equity, 2))

    # Metrics.
    wins = [t for t in trades if t["pnl"] > 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    curve = np.array(equity_curve) if equity_curve else np.array([starting_equity])
    running_peak = np.maximum.accumulate(curve)
    drawdowns = (running_peak - curve) / running_peak
    max_dd = float(drawdowns.max() * 100) if len(drawdowns) else 0.0
    rets = np.diff(curve) / curve[:-1] if len(curve) > 1 else np.array([0.0])
    sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(252)) if np.std(rets) > 0 else 0.0

    return BacktestResult(
        starting_equity=starting_equity,
        ending_equity=round(equity, 2),
        total_return_pct=round((equity / starting_equity - 1) * 100, 2),
        num_trades=len(trades),
        win_rate=round(win_rate, 4),
        max_drawdown_pct=round(max_dd, 2),
        sharpe=round(sharpe, 3),
        equity_curve=equity_curve,
        trades=trades,
    )
