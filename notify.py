"""
Trade alert logger — writes to trades.log and prints to stdout.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

TRADE_LOG = Path(__file__).parent / "trades.log"
logger = logging.getLogger(__name__)


def _write(line: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"[{ts}] {line}"
    with open(TRADE_LOG, "a") as f:
        f.write(entry + "\n")
    print(entry)


def alert_buy(symbol: str, dollars: float, shares: float, price: float, signal: str, k: float, rsi: float) -> None:
    label = "BEST BUY" if signal == "best_buy" else "WATCH BUY"
    _write(f"🟢 {label}  {symbol:6s}  ${dollars:.2f} → {shares:.4f} shares @ ${price:.4f}  |  RSI={rsi:.1f}  K={k:.1f}")


def alert_sell(symbol: str, shares: float, price: float, k_level: int, pct: int) -> None:
    proceeds = shares * price
    _write(f"🔴 SELL     {symbol:6s}  {shares:.4f} shares @ ${price:.4f}  (${proceeds:.2f})  |  tranche K≥{k_level} ({pct}%)")


def alert_scan_table(rows: list[dict]) -> None:
    header = f"\n{'─'*68}\n{'Symbol':<6} {'Price':>8}  {'RSI14':>5}  {'K':>6} {'D':>6}  {'Signal'}\n{'─'*68}"
    print(header)
    with open(TRADE_LOG, "a") as f:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        f.write(f"\n[{ts}] SCAN\n")
        f.write(header + "\n")
        for r in rows:
            line = f"{r['sym']:<6} {r['price']:>8.2f}  {r['rsi']:>5.1f}  {r['k']:>6.1f} {r['d']:>6.1f}  {r.get('signal','')}"
            print(line)
            f.write(line + "\n")
    print("─" * 68)


def alert_error(symbol: str, msg: str) -> None:
    logger.warning(f"{symbol}: {msg}")
