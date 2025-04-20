import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def log_to_google_sheets(sheet_name, df):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = st.secrets["gspread_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Stock Rankings").worksheet(sheet_name)

        # Clear the sheet
        sheet.clear()

        # Prepare data
        data = [df.columns.tolist()] + df.values.tolist()

        # Update all at once
        sheet.update("A1", data)
    except Exception as e:
        st.warning(f"⚠️ Could not update Google Sheet: {e}")
