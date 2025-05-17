import pandas as pd
import gspread
import logging
from datetime import datetime
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
from indicators import calculate_scores
from zerodha import get_stock_data
from sheet_logger import log_to_google_sheets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load credentials from secrets (assuming Streamlit-style TOML)
creds_dict = {
    # replace with actual secret loading logic in deployment
    "type": "service_account",
    "project_id": "your_project_id",
    "private_key_id": "your_key_id",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "your_email@project.iam.gserviceaccount.com",
    "client_id": "your_client_id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your_email%40project.iam.gserviceaccount.com"
}

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Load API key/token from Google Sheet
token_sheet = client.open("ZerodhaTokenStore").sheet1
api_key, _, access_token = token_sheet.get_all_values()[0][:3]

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Get symbol list from Google Sheet
ltp_sheet = client.open("LiveLTPStore").sheet1
symbols = [row[0] for row in ltp_sheet.get_all_values()[1:] if row]

records = []

for symbol in symbols:
    try:
        df_ohlc = get_stock_data(kite, symbol, interval="15minute", days=2)
        if df_ohlc.empty:
            logger.warning(f"⚠️ No data for {symbol}")
            continue

        scores = calculate_scores(df_ohlc)
        scores["Symbol"] = symbol
        records.append(scores)
        logger.info(f"✅ Processed {symbol}: {scores['TMV Score']}")
    except Exception as e:
        logger.error(f"❌ Failed to process {symbol}: {e}")

# Convert to DataFrame and sort
if records:
    df_scores = pd.DataFrame(records)
    df_scores = df_scores[["Symbol", "TMV Score", "Trend Score", "Momentum Score", "Volume Score", "Trend Direction", "Reversal Probability"]]
    df_scores.sort_values("TMV Score", ascending=False, inplace=True)

    # Log to Google Sheets
    log_to_google_sheets("LiveScores", df_scores)
    logger.info("✅ TMV scores logged to LiveScores sheet.")
else:
    logger.warning("⚠️ No scores to log.")
