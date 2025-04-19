import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from typing import Union

# Google Sheets config
SHEET_NAME = "StockRankerLogs"
CREDENTIALS_FILE = "zerodhatokensaver-1b53153ffd25.json"

def log_to_sheet(df: pd.DataFrame, timeframe: str) -> None:
    """
    Logs the given DataFrame to Google Sheets under a sheet named after the timeframe and current date.
    
    Parameters:
        df (pd.DataFrame): The data to log.
        timeframe (str): Timeframe used in the analysis (e.g. '15min', '1h', '1d').
    """
    try:
        # Define scope and authenticate
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        # Open or create the main sheet
        try:
            sheet = client.open(SHEET_NAME)
        except gspread.SpreadsheetNotFound:
            sheet = client.create(SHEET_NAME)

        # Create a new tab for each log entry (optional: reuse one per timeframe)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tab_name = f"{timeframe}_{date_str}"

        # Google Sheets tab name limit is 100 characters
        if len(tab_name) > 95:
            tab_name = tab_name[:95]

        # Add new worksheet and log data
        worksheet = sheet.add_worksheet(title=tab_name, rows="100", cols="20")
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())

    except Exception as e:
        print(f"[❌] Failed to log to Google Sheets: {e}")
