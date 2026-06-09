"""
Runs the strategy scan every 5 minutes.
"""

import logging
import time

from strategy import run_scan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 300  # 5 minutes


def run() -> None:
    logger.info("Trading bot started — scanning every 5 minutes")
    while True:
        try:
            run_scan()
        except Exception as e:
            logger.error(f"Scan failed: {e}", exc_info=True)
        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
