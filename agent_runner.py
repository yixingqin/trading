"""
GitHub Actions entry point: runs the strategy via the Claude API.

Claude fetches candle data, calculates Stoch RSI signals, and executes
trades through the Robinhood MCP server — all in one API call.
"""

import os
import sys
import json
import anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ROBINHOOD_MCP_URL = os.environ.get("ROBINHOOD_MCP_URL", "https://agent.robinhood.com/mcp/trading")
ROBINHOOD_MCP_TOKEN = os.environ["ROBINHOOD_MCP_TOKEN"]
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")

# Load strategy config from config.py values (keep single source of truth)
sys.path.insert(0, os.path.dirname(__file__))
from config import (
    WATCHLIST, POSITION_SIZE_PCT, ACCOUNT_SIZE, EXIT_TRANCHES,
    BEST_BUY_K_THRESHOLD, BEST_BUY_RSI_THRESHOLD,
    WATCH_K_THRESHOLD, WATCH_RSI_THRESHOLD,
)

STRATEGY_PROMPT = f"""
You are an automated trading bot executing a 4h Stoch RSI strategy. Today's date/time is current market time.

## Strategy Rules

**Indicators:** 4h Stoch RSI (3,3,14,14) with RSI 14
- Best Buy signal: %K < {BEST_BUY_K_THRESHOLD} AND RSI ≤ {BEST_BUY_RSI_THRESHOLD}
- Watch signal:    %K < {WATCH_K_THRESHOLD}  AND RSI ≤ {WATCH_RSI_THRESHOLD}

**Position sizing:** ${ACCOUNT_SIZE * POSITION_SIZE_PCT:.0f} per position (5% of ${ACCOUNT_SIZE:.0f} account)

**Staged exits (25% each):** sell at %K ≥ 75 / 80 / 85 / 90

**Account:** use the agentic account (agentic_allowed=true, account_number ends in 8949)

## Current State File
{_load_state()}

## Watchlist
{', '.join(WATCHLIST)}

## Instructions

1. Fetch current account buying power via `get_portfolio`.
2. For EACH symbol in the watchlist:
   a. Fetch 4h OHLCV candle data using Yahoo Finance API:
      GET https://query1.finance.yahoo.com/v8/finance/chart/SYMBOL?interval=1h&range=30d
      Then resample 1h → 4h (group by 4h buckets starting 9:30 ET).
   b. Calculate Stoch RSI (3,3,14,14) and RSI(14) on the 4h closes.
      - RSI = Wilder's EMA smoothing
      - Stoch RSI raw = 100 × (RSI - min(RSI,14)) / (max(RSI,14) - min(RSI,14))
      - %K = 3-period SMA of raw Stoch RSI
      - %D = 3-period SMA of %K
   c. Apply entry/exit rules:
      - If symbol is in state (open position): check exit tranches not yet hit.
      - If symbol is NOT in state and signal is best_buy or watch: enter if buying_power ≥ $10.
3. {"LOG all signals and intended actions but place NO orders (DRY RUN)." if DRY_RUN else "Place orders via `place_equity_order` for any signals triggered."}
4. Print a final summary table: symbol | %K | RSI | signal | action taken.
"""


def _load_state() -> str:
    from pathlib import Path
    state_file = Path(__file__).parent / "state.json"
    if state_file.exists():
        return state_file.read_text()
    return "{}"


def _save_state(text: str) -> None:
    """Claude may output updated state JSON in a ```state.json block."""
    import re
    from pathlib import Path
    match = re.search(r"```state\.json\s*\n(.*?)```", text, re.DOTALL)
    if match:
        Path(__file__).parent.joinpath("state.json").write_text(match.group(1).strip())


def run() -> None:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"Starting scan — DRY_RUN={DRY_RUN}")

    response = client.beta.messages.create(
        model="claude-opus-4-8",
        max_tokens=16000,
        messages=[{"role": "user", "content": STRATEGY_PROMPT}],
        mcp_servers=[
            {
                "type": "url",
                "url": ROBINHOOD_MCP_URL,
                "name": "robinhood",
                "authorization_token": ROBINHOOD_MCP_TOKEN,
            }
        ],
        betas=["mcp-client-2025-04-04"],
    )

    # Print full response
    for block in response.content:
        if hasattr(block, "text"):
            print(block.text)

    # Persist any state updates Claude emitted
    full_text = " ".join(b.text for b in response.content if hasattr(b, "text"))
    _save_state(full_text)

    print(f"\nInput tokens: {response.usage.input_tokens}  Output: {response.usage.output_tokens}")


if __name__ == "__main__":
    run()
