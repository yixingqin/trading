"""
Robinhood MCP client.

Trades are routed to the agentic cash account (agentic_allowed=true).
Historical OHLCV data comes from yfinance (Robinhood MCP has no candles endpoint).

MCP protocol: POST tools/call to the MCP URL with a Bearer token.
The token is the OAuth access token from the Robinhood MCP connector in claude.ai.
"""

import json
import logging
import time
import uuid
import requests
import pandas as pd
import yfinance as yf
from config import MCP_URL, MCP_TOKEN, TRADING_ACCOUNT, CANDLE_INTERVAL

logger = logging.getLogger(__name__)

_rpc_id = 0

# Map config interval name to yfinance interval string
_YF_INTERVAL = {
    "4hour": "1h",   # yfinance has no 4h; we resample from 1h
    "1hour": "1h",
    "1day": "1d",
}


def _rpc_id_next() -> int:
    global _rpc_id
    _rpc_id += 1
    return _rpc_id


def _call(tool_name: str, arguments: dict) -> dict:
    """Call a Robinhood MCP tool via the tools/call JSON-RPC method."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MCP_TOKEN}",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": _rpc_id_next(),
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    for attempt in range(4):
        try:
            resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
            result = data.get("result", {})
            # MCP wraps the payload in content[].text as a JSON string
            content = result.get("content", [])
            if content and content[0].get("type") == "text":
                return json.loads(content[0]["text"])
            return result
        except requests.RequestException as e:
            wait = 2 ** attempt
            logger.warning(f"MCP call failed (attempt {attempt+1}): {e}. Retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"MCP tool {tool_name} failed after 4 attempts")


# ── Market data (yfinance) ────────────────────────────────────────────────────

def get_candles(symbol: str, interval: str = CANDLE_INTERVAL, count: int = 100) -> pd.DataFrame:
    """
    Fetch OHLCV candles via yfinance and return a DataFrame with DatetimeIndex.
    4h candles are assembled by resampling 1h bars.
    """
    yf_interval = _YF_INTERVAL.get(interval, "1h")
    # Fetch enough history: 100 × 4h ≈ 400 hours ≈ 17 days of trading; use 30d to be safe
    period = "60d" if interval == "4hour" else "30d"
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=yf_interval, auto_adjust=True)
    if df.empty:
        return pd.DataFrame()

    df.index = df.index.tz_localize(None) if df.index.tzinfo else df.index
    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]]

    if interval == "4hour":
        df = (
            df.resample("4h", offset="9h30min")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna(subset=["close"])
        )

    return df.tail(count)


# ── Account ───────────────────────────────────────────────────────────────────

def get_account() -> dict:
    result = _call("get_portfolio", {"account_number": TRADING_ACCOUNT})
    return result.get("data", result)


def buying_power() -> float:
    result = _call("get_portfolio", {"account_number": TRADING_ACCOUNT})
    data = result.get("data", {})
    # cash buying power for the agentic cash account
    bp = (
        data.get("cash_available_for_withdrawal")
        or data.get("buying_power")
        or data.get("unallocated_margin_cash")
        or 0
    )
    return float(bp)


def get_positions() -> list[dict]:
    result = _call("get_equity_positions", {"account_number": TRADING_ACCOUNT})
    data = result.get("data", result)
    return data.get("results", [])


def get_open_orders() -> list[dict]:
    result = _call("get_equity_orders", {
        "account_number": TRADING_ACCOUNT,
        "state": "queued",
    })
    data = result.get("data", result)
    return data.get("orders", [])


# ── Quotes ────────────────────────────────────────────────────────────────────

def get_quote(symbol: str) -> dict:
    result = _call("get_equity_quotes", {"symbols": [symbol]})
    data = result.get("data", result)
    quotes = data.get("quotes", [data]) if isinstance(data, dict) else data
    return quotes[0] if quotes else {}


# ── Order execution ───────────────────────────────────────────────────────────

def place_market_buy(symbol: str, dollar_amount: float) -> dict:
    logger.info(f"BUY {symbol} ~${dollar_amount:.2f}")
    result = _call("place_equity_order", {
        "account_number": TRADING_ACCOUNT,
        "symbol": symbol,
        "side": "buy",
        "type": "market",
        "dollar_amount": f"{dollar_amount:.2f}",
        "time_in_force": "gfd",
        "ref_id": str(uuid.uuid4()),
    })
    return result.get("data", result)


def place_market_sell(symbol: str, quantity: float) -> dict:
    logger.info(f"SELL {symbol} qty={quantity}")
    result = _call("place_equity_order", {
        "account_number": TRADING_ACCOUNT,
        "symbol": symbol,
        "side": "sell",
        "type": "market",
        "quantity": str(round(quantity, 6)),
        "time_in_force": "gfd",
        "ref_id": str(uuid.uuid4()),
    })
    return result.get("data", result)
