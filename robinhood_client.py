"""
Robinhood MCP client.

The Robinhood MCP server exposes JSON-RPC 2.0 over HTTP at
https://agent.robinhood.com/mcp/trading

Authentication uses a Bearer token set in ROBINHOOD_API_TOKEN.
All trades are routed to the agentic cash account (TRADING_ACCOUNT_ID).
"""

import json
import logging
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from config import MCP_URL, MCP_TOKEN, TRADING_ACCOUNT, CANDLE_INTERVAL

logger = logging.getLogger(__name__)

_rpc_id = 0


def _rpc_id_next() -> int:
    global _rpc_id
    _rpc_id += 1
    return _rpc_id


def _call(method: str, params: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MCP_TOKEN}",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": _rpc_id_next(),
        "method": method,
        "params": params,
    }
    for attempt in range(4):
        try:
            resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
            return data.get("result", {})
        except requests.RequestException as e:
            wait = 2 ** attempt
            logger.warning(f"MCP call failed (attempt {attempt+1}): {e}. Retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"MCP call {method} failed after 4 attempts")


# ── Market data ──────────────────────────────────────────────────────────────

def get_candles(symbol: str, interval: str = CANDLE_INTERVAL, count: int = 100) -> pd.DataFrame:
    """Fetch OHLCV candles. Returns DataFrame with DatetimeIndex."""
    result = _call("market.candles", {
        "symbol": symbol,
        "interval": interval,
        "count": count,
        "account_id": TRADING_ACCOUNT,
    })
    candles = result.get("candles", [])
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df


def get_quote(symbol: str) -> dict:
    return _call("market.quote", {"symbol": symbol, "account_id": TRADING_ACCOUNT})


def get_account() -> dict:
    return _call("account.get", {"account_id": TRADING_ACCOUNT})


def get_positions() -> list[dict]:
    result = _call("account.positions", {"account_id": TRADING_ACCOUNT})
    return result.get("positions", [])


def get_open_orders() -> list[dict]:
    result = _call("orders.list", {"account_id": TRADING_ACCOUNT, "status": "open"})
    return result.get("orders", [])


# ── Order execution ───────────────────────────────────────────────────────────

def place_market_buy(symbol: str, dollar_amount: float) -> dict:
    logger.info(f"BUY {symbol} ~${dollar_amount:.2f}")
    return _call("orders.place", {
        "account_id": TRADING_ACCOUNT,
        "symbol": symbol,
        "side": "buy",
        "type": "market",
        "dollar_amount": round(dollar_amount, 2),
        "time_in_force": "gfd",
    })


def place_market_sell(symbol: str, quantity: float) -> dict:
    logger.info(f"SELL {symbol} qty={quantity}")
    return _call("orders.place", {
        "account_id": TRADING_ACCOUNT,
        "symbol": symbol,
        "side": "sell",
        "type": "market",
        "quantity": quantity,
        "time_in_force": "gfd",
    })


def buying_power() -> float:
    acct = get_account()
    return float(acct.get("buying_power", 0))
