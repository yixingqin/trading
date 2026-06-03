"""
Lightweight JSON-backed state: tracks open positions and which exit tranches
have already been sold.

Schema:
{
  "RKLB": {
    "entry_price": 12.34,
    "shares": 20.5,
    "entry_time": "2026-06-01T10:00:00",
    "dollar_invested": 250.0,
    "tranches_sold": [75, 80]   # k-levels already exited
  },
  ...
}
"""

import json
import os
from pathlib import Path

STATE_FILE = Path(__file__).parent / "state.json"


def _load() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def _save(data: dict) -> None:
    STATE_FILE.write_text(json.dumps(data, indent=2))


def get_position(symbol: str) -> dict | None:
    return _load().get(symbol)


def all_positions() -> dict:
    return _load()


def open_position(symbol: str, shares: float, entry_price: float, dollar_invested: float) -> None:
    data = _load()
    from datetime import datetime
    data[symbol] = {
        "entry_price": entry_price,
        "shares": shares,
        "entry_time": datetime.utcnow().isoformat(),
        "dollar_invested": dollar_invested,
        "tranches_sold": [],
    }
    _save(data)


def record_tranche_sold(symbol: str, k_level: int, shares_sold: float) -> None:
    data = _load()
    if symbol not in data:
        return
    data[symbol]["tranches_sold"].append(k_level)
    data[symbol]["shares"] = max(0, data[symbol]["shares"] - shares_sold)
    _save(data)


def close_position(symbol: str) -> None:
    data = _load()
    data.pop(symbol, None)
    _save(data)
