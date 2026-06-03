"""
GitHub Actions entry point.

GitHub Actions has full internet access, so:
- yfinance fetches 4h candle data directly (free, no key needed)
- Python calculates Stoch RSI signals
- Claude API executes trades via the Robinhood MCP server
"""

import os
import sys
import json
import anthropic

sys.path.insert(0, os.path.dirname(__file__))

from config import WATCHLIST, POSITION_SIZE_PCT, ACCOUNT_SIZE
import state
from robinhood_client import get_candles
from indicators import current_signals, exit_tranches_hit

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")
ROBINHOOD_MCP_URL = os.environ.get("ROBINHOOD_MCP_URL", "https://agent.robinhood.com/mcp/trading")
ROBINHOOD_MCP_TOKEN = os.environ["ROBINHOOD_MCP_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TRADING_ACCOUNT = os.environ.get("TRADING_ACCOUNT_ID", "692348949")


def build_order_prompt(signals: list[dict], positions: dict) -> str:
    position_summary = json.dumps(positions, indent=2) if positions else "none"
    signal_lines = "\n".join(
        f"- {s['symbol']}: %K={s['k']} RSI={s['rsi']} signal={s['signal']} "
        f"{'(position open, tranches_sold=' + str(positions[s['symbol']]['tranches_sold']) + ')' if s['symbol'] in positions else ''}"
        for s in signals
    )
    dollar_size = ACCOUNT_SIZE * POSITION_SIZE_PCT

    return f"""
You are executing trades for a Stoch RSI strategy. Account number: {TRADING_ACCOUNT} (agentic_allowed=true).

## Current signals (4h Stoch RSI 3,3,14,14 + RSI 14)

{signal_lines}

## Open positions
{position_summary}

## Rules
- best_buy or watch signal + no open position → buy ~${dollar_size:.0f} (market order, dollar_amount)
- Open position + %K ≥ 75/80/85/90 → sell 25% tranche if that level not yet in tranches_sold
- {'THIS IS A DRY RUN. Do NOT place any orders. Just describe what you would do.' if DRY_RUN else 'Place orders now using place_equity_order.'}

## Required output format
After acting, output a JSON block tagged ```actions``` listing what was done:
[{{"symbol":"X","action":"buy","dollars":250}}, {{"symbol":"Y","action":"sell_tranche","k_level":75,"shares":10.5}}]
If nothing to do, output: ```actions\n[]\n```
"""


def run() -> None:
    print(f"=== Stoch RSI scan — DRY_RUN={DRY_RUN} ===\n")

    # ── 1. Fetch signals for all watchlist symbols ────────────────────────────
    signals = []
    for symbol in WATCHLIST:
        try:
            df = get_candles(symbol)
            if df.empty or len(df) < 50:
                print(f"{symbol}: insufficient data")
                continue
            sig = current_signals(df)
            sig["symbol"] = symbol
            signals.append(sig)
            print(f"{symbol:6s}  k={sig['k']:6.2f}  rsi={sig['rsi']:6.2f}  → {sig['signal']}")
        except Exception as e:
            print(f"{symbol}: error — {e}")

    # ── 2. Filter to actionable signals only ─────────────────────────────────
    positions = state.all_positions()
    actionable = []
    for sig in signals:
        sym = sig["symbol"]
        if sig["signal"] in ("best_buy", "watch") and sym not in positions:
            actionable.append(sig)
        elif sym in positions:
            pos = positions[sym]
            if exit_tranches_hit(sig["k"], pos["tranches_sold"]):
                actionable.append(sig)

    if not actionable:
        print("\nNo actionable signals this scan.")
        return

    print(f"\nActionable: {[s['symbol'] for s in actionable]}")

    # ── 3. Hand off to Claude + Robinhood MCP for execution ──────────────────
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = build_order_prompt(actionable, positions)

    response = client.beta.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        mcp_servers=[{
            "type": "url",
            "url": ROBINHOOD_MCP_URL,
            "name": "robinhood",
            "authorization_token": ROBINHOOD_MCP_TOKEN,
        }],
        betas=["mcp-client-2025-04-04"],
    )

    # ── 4. Parse actions and update local state ───────────────────────────────
    import re
    full_text = "".join(b.text for b in response.content if hasattr(b, "text"))
    print("\n" + full_text)

    match = re.search(r"```actions\s*\n(.*?)```", full_text, re.DOTALL)
    if not match:
        return

    actions = json.loads(match.group(1).strip())
    for act in actions:
        sym = act["symbol"]
        if act["action"] == "buy" and not DRY_RUN:
            # Claude placed the order; record in state (price unknown until fill)
            # Use last close as approximate entry price
            sig = next((s for s in signals if s["symbol"] == sym), {})
            state.open_position(sym, shares=0, entry_price=0, dollar_invested=act.get("dollars", 0))
        elif act["action"] == "sell_tranche" and not DRY_RUN:
            state.record_tranche_sold(sym, act["k_level"], act.get("shares", 0))
            pos = state.get_position(sym)
            if pos and len(pos["tranches_sold"]) >= 4:
                state.close_position(sym)
                print(f"{sym}: fully closed")


if __name__ == "__main__":
    run()
