"""
Strategy engine: scans watchlist, executes entries and staged exits.
"""

import logging
from config import (
    WATCHLIST, POSITION_SIZE_PCT, ACCOUNT_SIZE, EXIT_TRANCHES,
)
import robinhood_client as rh
import state
from indicators import current_signals, exit_tranches_hit

logger = logging.getLogger(__name__)


def position_size_dollars() -> float:
    """5% of account. Use live buying power as a sanity cap."""
    target = ACCOUNT_SIZE * POSITION_SIZE_PCT
    bp = rh.buying_power()
    return min(target, bp * 0.99)  # leave 1% buffer


def run_scan() -> None:
    logger.info("── Starting scan ──")

    for symbol in WATCHLIST:
        try:
            _check_symbol(symbol)
        except Exception as e:
            logger.error(f"{symbol}: error during scan: {e}")

    logger.info("── Scan complete ──")


def _check_symbol(symbol: str) -> None:
    df = rh.get_candles(symbol)
    if df.empty:
        logger.warning(f"{symbol}: no candle data")
        return

    sig = current_signals(df)
    k = sig["k"]
    logger.info(f"{symbol}: k={k} rsi={sig['rsi']} signal={sig['signal']}")

    existing = state.get_position(symbol)

    # ── Exit logic (check before entry) ──────────────────────────────────────
    if existing:
        filled = existing["tranches_sold"]
        to_exit = exit_tranches_hit(k, filled)
        for level in to_exit:
            _execute_tranche_exit(symbol, existing, level)
        # Reload after possible mutations
        existing = state.get_position(symbol)

    # ── Entry logic ───────────────────────────────────────────────────────────
    if sig["signal"] in ("best_buy", "watch") and not existing:
        _execute_entry(symbol, sig)


def _execute_entry(symbol: str, sig: dict) -> None:
    dollars = position_size_dollars()
    if dollars < 10:
        logger.warning(f"{symbol}: insufficient buying power (${dollars:.2f}), skipping")
        return

    label = "BEST BUY" if sig["signal"] == "best_buy" else "WATCH"
    logger.info(f"{symbol}: [{label}] entering ~${dollars:.2f}  k={sig['k']} rsi={sig['rsi']}")

    order = rh.place_market_buy(symbol, dollars)
    order_id = order.get("id", "?")
    filled_qty = float(order.get("filled_quantity", 0))
    avg_price = float(order.get("average_price", 0))

    if filled_qty <= 0:
        logger.error(f"{symbol}: buy order {order_id} not filled immediately — check manually")
        return

    state.open_position(symbol, filled_qty, avg_price, dollars)
    logger.info(f"{symbol}: bought {filled_qty} @ ${avg_price:.4f}  order={order_id}")


def _execute_tranche_exit(symbol: str, pos: dict, k_level: int) -> None:
    tranche_pct = dict(EXIT_TRANCHES)[k_level]
    shares_to_sell = round(pos["shares"] * tranche_pct, 6)

    if shares_to_sell <= 0:
        return

    logger.info(f"{symbol}: exit tranche @k≥{k_level} — selling {shares_to_sell} shares ({tranche_pct*100:.0f}%)")
    order = rh.place_market_sell(symbol, shares_to_sell)
    order_id = order.get("id", "?")
    avg_price = float(order.get("average_price", 0))

    state.record_tranche_sold(symbol, k_level, shares_to_sell)
    logger.info(f"{symbol}: sold {shares_to_sell} @ ${avg_price:.4f}  order={order_id}")

    # If all 4 tranches done, clean up
    updated = state.get_position(symbol)
    if updated and len(updated["tranches_sold"]) >= 4:
        state.close_position(symbol)
        logger.info(f"{symbol}: position fully closed")
