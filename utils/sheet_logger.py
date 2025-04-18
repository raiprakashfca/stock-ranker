import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import streamlit as st

def log_to_google_sheets(sheet_name, df):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["gspread_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    sheet = client.open("Stock Rankings")

    try:
        worksheet = sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=sheet_name, rows="100", cols="20")

    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())
