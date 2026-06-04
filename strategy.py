"""
Strategy engine: scans watchlist, executes entries and staged exits.
"""

import logging
import pandas as pd
from config import (
    WATCHLIST, POSITION_SIZE_PCT, ACCOUNT_SIZE, EXIT_TRANCHES,
    RSI_PERIOD, STOCH_RSI_RSI_PERIOD, STOCH_RSI_STOCH_PERIOD,
    STOCH_RSI_K, STOCH_RSI_D,
)
import robinhood_client as rh
import state
import notify
from indicators import rsi, stoch_rsi, current_signals, exit_tranches_hit

# Entry uses 4h candles; exits use 1h candles for faster reaction

logger = logging.getLogger(__name__)


def position_size_dollars() -> float:
    target = ACCOUNT_SIZE * POSITION_SIZE_PCT
    bp = rh.buying_power()
    return min(target, bp * 0.99)


def run_scan() -> None:
    logger.info("── Starting scan ──")
    rows = []

    for symbol in WATCHLIST:
        try:
            row = _scan_symbol(symbol)
            if row:
                rows.append(row)
        except Exception as e:
            logger.error(f"{symbol}: scan error: {e}")

    notify.alert_scan_table(rows)
    logger.info("── Scan complete ──")


def _scan_symbol(symbol: str) -> dict | None:
    # 4h candles for entry signals
    df4 = rh.get_candles(symbol)
    if df4.empty:
        logger.warning(f"{symbol}: no candle data")
        return None

    rsi14 = rsi(df4["close"], RSI_PERIOD)
    k4, d4 = stoch_rsi(
        df4["close"],
        rsi_period=STOCH_RSI_RSI_PERIOD,
        stoch_period=STOCH_RSI_STOCH_PERIOD,
        k_smooth=STOCH_RSI_K,
        d_smooth=STOCH_RSI_D,
    )
    latest_rsi = rsi14.iloc[-1]
    latest_k4 = k4.iloc[-1]
    latest_d4 = d4.iloc[-1]
    price = df4["close"].iloc[-1]

    # 1h candles for exit signals
    df1 = rh.get_candles_1h(symbol)
    if not df1.empty:
        k1, d1 = stoch_rsi(
            df1["close"],
            rsi_period=STOCH_RSI_RSI_PERIOD,
            stoch_period=STOCH_RSI_STOCH_PERIOD,
            k_smooth=STOCH_RSI_K,
            d_smooth=STOCH_RSI_D,
        )
        latest_k1 = k1.iloc[-1]
        latest_d1 = d1.iloc[-1]
    else:
        latest_k1, latest_d1 = latest_k4, latest_d4

    # Entry signal uses 4h K
    signal = "none"
    if latest_k4 < 10 and latest_rsi <= 50:
        signal = "best_buy"
    elif latest_k4 < 10 and latest_rsi <= 60:
        signal = "watch"

    existing = state.get_position(symbol)
    pnl_pct = None
    if existing:
        entry = existing.get("entry_price", 0)
        if entry > 0:
            pnl_pct = round((price - entry) / entry * 100, 2)

    row = {
        "sym": symbol,
        "price": price,
        "rsi": round(latest_rsi, 1),
        "k4": round(latest_k4, 1),
        "d4": round(latest_d4, 1),
        "k1": round(latest_k1, 1),
        "d1": round(latest_d1, 1),
        "signal": signal,
        "pnl_pct": pnl_pct,
    }

    # ── Exit logic uses 1h K ──────────────────────────────────────────────────
    if existing:
        filled = existing["tranches_sold"]
        to_exit = exit_tranches_hit(latest_k1, filled)
        for level in to_exit:
            _execute_tranche_exit(symbol, existing, level, price)
        existing = state.get_position(symbol)

    # ── Entry logic uses 4h K ─────────────────────────────────────────────────
    if signal in ("best_buy", "watch") and not existing:
        _execute_entry(symbol, signal, latest_k4, latest_rsi, price)

    return row


def _execute_entry(symbol: str, signal: str, k: float, rsi_val: float, last_price: float) -> None:
    dollars = position_size_dollars()
    if dollars < 10:
        logger.warning(f"{symbol}: insufficient buying power (${dollars:.2f}), skipping")
        return

    order = rh.place_market_buy(symbol, dollars)
    order_id = order.get("id", "?")
    filled_qty = float(order.get("filled_quantity", 0))
    avg_price = float(order.get("average_price", last_price))

    if filled_qty <= 0:
        logger.error(f"{symbol}: buy order {order_id} not filled — check manually")
        return

    state.open_position(symbol, filled_qty, avg_price, dollars)
    notify.alert_buy(symbol, dollars, filled_qty, avg_price, signal, k, rsi_val)


def _execute_tranche_exit(symbol: str, pos: dict, k_level: int, last_price: float) -> None:
    tranche_pct = dict(EXIT_TRANCHES)[k_level]
    shares_to_sell = round(pos["shares"] * tranche_pct, 6)
    if shares_to_sell <= 0:
        return

    order = rh.place_market_sell(symbol, shares_to_sell)
    order_id = order.get("id", "?")
    avg_price = float(order.get("average_price", last_price))

    state.record_tranche_sold(symbol, k_level, shares_to_sell)
    notify.alert_sell(symbol, shares_to_sell, avg_price, k_level, int(tranche_pct * 100))

    updated = state.get_position(symbol)
    if updated and len(updated["tranches_sold"]) >= 4:
        state.close_position(symbol)
        logger.info(f"{symbol}: position fully closed")
