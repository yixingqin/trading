"""
GitHub Actions entry point.

Claude API handles everything:
- web_search tool fetches candle/price data (free, no API key)
- Robinhood MCP tool places orders
No local dependencies on yfinance or pandas needed at runtime.
"""

import os
import re
import json
import anthropic

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")
ROBINHOOD_MCP_URL = os.environ.get("ROBINHOOD_MCP_URL", "https://agent.robinhood.com/mcp/trading")
ROBINHOOD_MCP_TOKEN = os.environ["ROBINHOOD_MCP_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TRADING_ACCOUNT = os.environ.get("TRADING_ACCOUNT_ID", "692348949")

WATCHLIST = [
    "HIVE", "SHAZ", "TE", "OUST", "FCEL", "SHMD", "VELO", "NBIS",
    "CRWV", "BE", "CRDO", "AAOI", "LITE", "OKLO", "ASTS", "RKLB",
    "PLTR", "NOW", "AUR", "HOOD",
]

PROMPT = f"""
You are an automated trading bot. Today's date/time is current market time.
Account number: {TRADING_ACCOUNT} (agentic_allowed=true, cash account).

## Strategy: 4h Stoch RSI (3,3,14,14) + RSI 14

**Indicators:**
- RSI(14) using Wilder EMA smoothing
- Stoch RSI raw = 100 × (RSI − min(RSI,14)) / (max(RSI,14) − min(RSI,14))
- %K = 3-period SMA of raw; %D = 3-period SMA of %K

**Entry signals:**
- Best Buy: %K < 10 AND RSI ≤ 50 → buy $250 (market order)
- Watch:    %K < 10 AND RSI ≤ 60 → buy $250 (market order)
- Only enter if no open position in that symbol

**Exit (staged, 25% each):**
- Sell 25% of position when %K first crosses ≥ 75, 80, 85, 90

## Open positions (state.json)
{_load_state()}

## Watchlist
{', '.join(WATCHLIST)}

## Steps to execute NOW

1. Use web_search to get hourly OHLCV data for each watchlist symbol
   (search "SYMBOL 1h historical prices" or fetch Yahoo Finance / Barchart).
   You need ~100 hours of closing prices to compute the indicators.

2. Calculate 4h Stoch RSI and RSI for each symbol (resample 1h→4h first:
   group into 4h buckets starting 09:30 ET, take last close of each bucket).

3. Check entry and exit conditions against open positions above.

4. {'DO NOT place any orders — this is a DRY RUN. Describe what you would do.' if DRY_RUN else 'Place orders via place_equity_order for every triggered signal.'}

5. Print a results table: symbol | %K | RSI | signal | action

6. Output a JSON block at the end:
```actions
[{{"symbol":"X","action":"buy","dollars":250}},{{"symbol":"Y","action":"sell_tranche","k_level":75,"shares":5.2}}]
```
Empty array if nothing triggered.
"""


def _load_state() -> str:
    from pathlib import Path
    f = Path(__file__).parent / "state.json"
    return f.read_text() if f.exists() else "{}"


def _save_state_updates(full_text: str, actions: list) -> None:
    import state
    for act in actions:
        sym = act.get("symbol")
        if not sym or DRY_RUN:
            continue
        if act.get("action") == "buy":
            state.open_position(sym, shares=0, entry_price=0, dollar_invested=act.get("dollars", 250))
        elif act.get("action") == "sell_tranche":
            state.record_tranche_sold(sym, act["k_level"], act.get("shares", 0))
            import sys; sys.path.insert(0, os.path.dirname(__file__))
            pos = state.get_position(sym)
            if pos and len(pos["tranches_sold"]) >= 4:
                state.close_position(sym)
                print(f"{sym}: fully closed")


def run() -> None:
    print(f"=== Stoch RSI scan  DRY_RUN={DRY_RUN} ===\n")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.beta.messages.create(
        model="claude-opus-4-8",
        max_tokens=16000,
        messages=[{"role": "user", "content": PROMPT}],
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        mcp_servers=[{
            "type": "url",
            "url": ROBINHOOD_MCP_URL,
            "name": "robinhood",
            "authorization_token": ROBINHOOD_MCP_TOKEN,
        }],
        betas=["mcp-client-2025-04-04"],
    )

    full_text = "".join(b.text for b in response.content if hasattr(b, "text"))
    print(full_text)

    match = re.search(r"```actions\s*\n(.*?)```", full_text, re.DOTALL)
    if match:
        actions = json.loads(match.group(1).strip())
        _save_state_updates(full_text, actions)

    print(f"\nTokens used — input: {response.usage.input_tokens}  output: {response.usage.output_tokens}")


if __name__ == "__main__":
    run()
