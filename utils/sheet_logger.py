# utils/sheet_logger.py

import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials

def log_to_google_sheets(sheet_name: str, df):
    """
    Logs the final DataFrame into the specified tab of the Google Sheet.
    """
    try:
        # Scope and credentials from Streamlit secrets
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["gspread_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)

        # Open target workbook and worksheet
        sheet = client.open("Stock Rankings")
        if sheet_name not in [ws.title for ws in sheet.worksheets()]:
            sheet.add_worksheet(title=sheet_name, rows="100", cols="30")
        worksheet = sheet.worksheet(sheet_name)

        # Clear old contents
        worksheet.clear()

        # Prepare and upload new data
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())

    except Exception as e:
        raise RuntimeError(f"❌ Failed to log to Google Sheet: {e}")
