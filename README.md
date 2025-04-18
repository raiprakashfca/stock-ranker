
# StockRanker Multi-Timeframe App

## Features
- Ranks heavyweight Indian stocks based on Trend, Momentum, and Volume indicators.
- Supports 3 timeframes: 15-minute, 1-hour, and daily.
- Uses Zerodha Kite Connect API for live OHLCV data.
- Logs results to Google Sheets automatically.

## Setup Instructions
1. Install requirements:
```bash
pip install -r requirements.txt
```
2. Run the app:
```bash
streamlit run app.py
```

## Google Sheets Setup
- Set up `secrets.toml` or Google Sheet authentication logic in `sheet_logger.py`.
