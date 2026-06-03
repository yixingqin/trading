"""
Runs the strategy scan every 4 hours, aligned to 9:30 ET candle boundaries.
Candle closes: 9:30, 13:30, 17:30, 21:30 ET (we scan ~30s after close).
"""

import logging
import time
from datetime import datetime, timezone
import pytz

from strategy import run_scan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")

# 4h candle close times in ET (hour, minute)
CANDLE_CLOSES_ET = [(9, 30), (13, 30), (17, 30), (21, 30)]
SCAN_DELAY_SECONDS = 30  # wait for candle to finalize


def seconds_until_next_scan() -> float:
    now_et = datetime.now(ET)
    today = now_et.date()
    candidates = []
    for h, m in CANDLE_CLOSES_ET:
        t = ET.localize(datetime(today.year, today.month, today.day, h, m, SCAN_DELAY_SECONDS))
        candidates.append(t)
        # Also tomorrow's first window in case we're past all today's windows
        from datetime import timedelta
        tomorrow = today + timedelta(days=1)
        t2 = ET.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, h, m, SCAN_DELAY_SECONDS))
        candidates.append(t2)

    future = [t for t in candidates if t > now_et]
    next_scan = min(future)
    delta = (next_scan - now_et).total_seconds()
    logger.info(f"Next scan at {next_scan.strftime('%Y-%m-%d %H:%M:%S %Z')} ({delta/60:.1f} min)")
    return delta


def run() -> None:
    logger.info("Trading bot started")
    while True:
        wait = seconds_until_next_scan()
        time.sleep(wait)
        try:
            run_scan()
        except Exception as e:
            logger.error(f"Scan failed: {e}", exc_info=True)


if __name__ == "__main__":
    run()
