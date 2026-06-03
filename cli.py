"""
Manual CLI for inspecting state and running one-off scans.

Usage:
  python cli.py scan          # run a full watchlist scan now
  python cli.py status        # show open positions and current k values
  python cli.py quote RKLB    # show current signals for a symbol
  python cli.py account       # show buying power
"""

import sys
import json
import logging
from config import WATCHLIST
import robinhood_client as rh
import state
from indicators import current_signals

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def cmd_scan():
    from strategy import run_scan
    run_scan()


def cmd_status():
    positions = state.all_positions()
    if not positions:
        print("No open positions in state.json")
        return
    for sym, pos in positions.items():
        df = rh.get_candles(sym)
        sig = current_signals(df) if not df.empty else {}
        k = sig.get("k", "?")
        print(f"{sym:6s}  entry=${pos['entry_price']:.4f}  shares={pos['shares']:.4f}"
              f"  tranches_sold={pos['tranches_sold']}  current_k={k}")


def cmd_quote(symbol: str):
    df = rh.get_candles(symbol)
    if df.empty:
        print(f"No data for {symbol}")
        return
    sig = current_signals(df)
    print(json.dumps(sig, indent=2))


def cmd_account():
    acct = rh.get_account()
    bp = acct.get("buying_power", "?")
    print(f"Buying power: ${float(bp):.2f}")
    print(json.dumps(acct, indent=2))


COMMANDS = {
    "scan": cmd_scan,
    "status": cmd_status,
    "quote": lambda: cmd_quote(sys.argv[2]) if len(sys.argv) > 2 else print("Usage: quote SYMBOL"),
    "account": cmd_account,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print(__doc__)
