import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

def log_to_google_sheets(sheet_name, df):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("zerodhatokensaver-1b53153ffd25.json", scope)
    client = gspread.authorize(creds)

    sheet = client.open("Stock Rankings")

    try:
        worksheet = sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=sheet_name, rows="100", cols="20")

    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())
