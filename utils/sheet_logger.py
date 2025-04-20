import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

def log_to_google_sheets(sheet_name: str, df: pd.DataFrame):
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(
        st.secrets["gspread_service_account"], scopes=scope
    )
    client = gspread.authorize(creds)

    spreadsheet = client.open("Stock Rankings")
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        worksheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="50")

    # Flatten MultiIndex if exists
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [' '.join(col).strip() for col in df.columns.values]

    # Upload headers and values
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())
