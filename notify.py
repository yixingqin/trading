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
    header = (
        f"\n{'─'*92}\n"
        f"{'Symbol':<6} {'Price':>8}  {'P&L%':>6}  {'RSI14':>5}  "
        f"{'4H-K':>6} {'4H-D':>6}  {'1H-K':>6} {'1H-D':>6}  {'Signal'}\n"
        f"{'─'*92}"
    )
    print(header)
    with open(TRADE_LOG, "a") as f:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        f.write(f"\n[{ts}] SCAN\n")
        f.write(header + "\n")
        for r in rows:
            pnl = r.get("pnl_pct")
            pnl_str = f"{pnl:>+.1f}%" if pnl is not None else "      "
            line = (
                f"{r['sym']:<6} {r['price']:>8.2f}  {pnl_str:>6}  {r['rsi']:>5.1f}  "
                f"{r.get('k4', r.get('k', 0)):>6.1f} {r.get('d4', r.get('d', 0)):>6.1f}  "
                f"{r.get('k1', r.get('k', 0)):>6.1f} {r.get('d1', r.get('d', 0)):>6.1f}  "
                f"{r.get('signal','')}"
            )
            print(line)
            f.write(line + "\n")
    print("─" * 92)


def alert_error(symbol: str, msg: str) -> None:
    logger.warning(f"{symbol}: {msg}")
