import os
from dotenv import load_dotenv

load_dotenv()

# Robinhood MCP
MCP_URL = os.getenv("ROBINHOOD_MCP_URL", "https://agent.robinhood.com/mcp/trading")
MCP_TOKEN = os.getenv("ROBINHOOD_API_TOKEN", "")
TRADING_ACCOUNT = os.getenv("TRADING_ACCOUNT_ID", "")

# Strategy: 4h Stoch RSI (3,3,14,14) with RSI 14
STOCH_RSI_K = 3
STOCH_RSI_D = 3
STOCH_RSI_RSI_PERIOD = 14
STOCH_RSI_STOCH_PERIOD = 14
RSI_PERIOD = 14
CANDLE_INTERVAL = "4hour"

# Entry thresholds
BEST_BUY_K_THRESHOLD = 10
BEST_BUY_RSI_THRESHOLD = 50
WATCH_K_THRESHOLD = 10
WATCH_RSI_THRESHOLD = 60

# Position sizing
POSITION_SIZE_PCT = float(os.getenv("POSITION_SIZE_PCT", "0.05"))
ACCOUNT_SIZE = float(os.getenv("ACCOUNT_SIZE", "5000"))

# Exit tranches: (k_level, pct_of_position)
EXIT_TRANCHES = [
    (75, 0.25),
    (80, 0.25),
    (85, 0.25),
    (90, 0.25),
]

# Watchlist
WATCHLIST = [
    "HIVE", "SHAZ", "TE", "OUST", "FCEL", "SHMD", "VELO", "NBIS",
    "CRWV", "BE", "CRDO", "AAOI", "LITE", "OKLO", "ASTS", "RKLB",
    "PLTR", "NOW", "AUR", "HOOD",
    # added
    "PANW", "PALU",
    "IREN", "NOK", "BB", "FSLY", "USAR", "RCAT", "PURR", "HIMS",
    "OPEN", "CLSK", "RIOT", "APLD", "CORZ", "BTI", "SMH", "NVDA",
    "ORCL", "AVGO", "AMD", "MU", "ASML", "INTC", "TSM", "GLW", "INFY",
]

# Scan every 4 hours aligned to market open (9:30 ET)
SCAN_INTERVAL_HOURS = 4
