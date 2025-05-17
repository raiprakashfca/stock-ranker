import pandas as pd
import gspread
import logging
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
from indicators import calculate_scores
from zerodha import get_stock_data
from sheet_logger import log_to_google_sheets
import schedule
import pytz
import time
import holidays
import sys
import os
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load credentials from environment variable
creds_dict = json.loads(os.environ["GSPREAD_CREDENTIALS_JSON"])

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Load API key/token from environment
api_key = os.environ["Z_API_KEY"]
access_token = os.environ["Z_ACCESS_TOKEN"]

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Get symbol list from Google Sheet
ltp_sheet = client.open("LiveLTPStore").sheet1
symbols = [row[0] for row in ltp_sheet.get_all_values()[1:] if row]

def is_market_open():
    india = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india)

    if now.weekday() >= 5:
        return False

    indian_holidays = holidays.India()
    if now.date() in indian_holidays:
        return False

    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    return market_open <= now <= market_close

def run_updater(days_back=2):
    records = []
    for symbol in symbols:
        try:
            df_ohlc = get_stock_data(kite, symbol, interval="15minute", days=days_back)
            if df_ohlc.empty:
                logger.warning(f"⚠️ No data for {symbol}")
                continue

            scores = calculate_scores(df_ohlc)
            scores["Symbol"] = symbol
            records.append(scores)
            logger.info(f"✅ Processed {symbol}: {scores['TMV Score']}")
        except Exception as e:
            logger.error(f"❌ Failed to process {symbol}: {e}")

    if records:
        df_scores = pd.DataFrame(records)
        df_scores = df_scores[["Symbol", "TMV Score", "Trend Score", "Momentum Score", "Volume Score", "Trend Direction", "Reversal Probability"]]
        df_scores.sort_values("TMV Score", ascending=False, inplace=True)
        log_to_google_sheets("LiveScores", df_scores)
        logger.info("✅ TMV scores logged to LiveScores sheet.")
    else:
        logger.warning("⚠️ No scores to log.")

def job():
    if is_market_open():
        print("✅ Market is open. Running TMV updater...")
        run_updater()
    else:
        print("🛌 Market is closed. Skipping run.")

if len(sys.argv) > 1 and sys.argv[1] == "test":
    print("🔬 Running in test mode using yesterday's data...")
    run_updater(days_back=3)
    sys.exit()

schedule.every(15).minutes.do(job)
print("📆 TMV updater scheduler started (IST)...")

while True:
    schedule.run_pending()
    time.sleep(60)
