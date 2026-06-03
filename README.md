# Stoch RSI Trading Bot

Automated 4h Stoch RSI strategy running against Robinhood via MCP.

## Strategy

- **Indicator**: Stoch RSI (3,3,14,14) + RSI 14 on 4h candles
- **Best buy**: %K < 10 **and** RSI ≤ 50
- **Watch entry**: %K < 10 **and** RSI ≤ 60
- **Position size**: 5% of account (~$250)
- **Staged exits**: sell 25% at %K ≥ 75 / 80 / 85 / 90

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in ROBINHOOD_API_TOKEN in .env
```

## Run

```bash
# Start the bot (scans at 9:30 / 13:30 / 17:30 / 21:30 ET)
python scheduler.py

# Manual commands
python cli.py scan          # run scan now
python cli.py status        # show open positions + current k
python cli.py quote RKLB    # signals for one symbol
python cli.py account       # buying power
```

## Files

| File | Purpose |
|------|---------|
| `config.py` | All strategy parameters |
| `indicators.py` | Stoch RSI + RSI calculation |
| `robinhood_client.py` | MCP API calls (candles, orders) |
| `strategy.py` | Entry/exit logic |
| `state.py` | JSON-backed position tracker |
| `scheduler.py` | 4h-aligned cron loop |
| `cli.py` | Manual inspection commands |

## Account

Trades execute on the agentic cash account (••••8949).  
Set `TRADING_ACCOUNT_ID` in `.env` to match your account number.
