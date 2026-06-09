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
import yfinance as yf
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

def _fetch_1h_raw(symbol: str, days: int = 60) -> pd.DataFrame:
    """Download 1h bars from yfinance and normalize columns."""
    period = f"{min(days, 729)}d"
    raw = yf.download(symbol, period=period, interval="1h", progress=False, auto_adjust=True)
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [c[0].lower() for c in raw.columns]
    else:
        raw.columns = [c.lower() for c in raw.columns]
    return raw[["open", "high", "low", "close", "volume"]]


def _candles_from_yfinance(symbol: str, count: int = 100) -> pd.DataFrame:
    """Fetch 4h OHLCV via yfinance (1h data resampled to 4h)."""
    days_needed = max(int(count * 4 / 6.5) + 10, 60)
    raw = _fetch_1h_raw(symbol, days=days_needed)
    if raw.empty:
        return pd.DataFrame()
    ohlcv = raw.resample("4h", offset="30min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return ohlcv.dropna(subset=["close"]).tail(count)


def get_candles_1h(symbol: str, count: int = 200) -> pd.DataFrame:
    """Fetch raw 1h OHLCV bars via yfinance."""
    try:
        days_needed = max(int(count / 6.5) + 10, 30)
        raw = _fetch_1h_raw(symbol, days=days_needed)
        if not raw.empty:
            return raw.dropna(subset=["close"]).tail(count)
    except Exception as e:
        logger.warning(f"yfinance 1h failed for {symbol}: {e}")
    return pd.DataFrame()


def get_candles(symbol: str, interval: str = CANDLE_INTERVAL, count: int = 100) -> pd.DataFrame:
    """Fetch OHLCV candles via yfinance, falling back to MCP."""
    try:
        df = _candles_from_yfinance(symbol, count)
        if not df.empty:
            return df
    except Exception as e:
        logger.warning(f"yfinance failed for {symbol}: {e}. Falling back to MCP.")

    # MCP fallback
    try:
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
    except Exception as e:
        logger.error(f"MCP candles also failed for {symbol}: {e}")
        return pd.DataFrame()


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
