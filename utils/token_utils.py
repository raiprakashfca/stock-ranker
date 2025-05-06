import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

SCOPE = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "ZerodhaTokenStore"
WORKSHEET  = "Sheet1"

def get_gsheet_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPE
    )
    return gspread.authorize(creds)

def load_credentials_from_gsheet():
    client = get_gsheet_client()
    sheet  = client.open(SHEET_NAME).worksheet(WORKSHEET)
    api_key, api_secret, access_token = (
        sheet.acell("A1").value,
        sheet.acell("B1").value,
        sheet.acell("C1").value
    )
    return api_key, api_secret, access_token

def save_token_to_gsheet(token: str):
    client = get_gsheet_client()
    sheet  = client.open(SHEET_NAME).worksheet(WORKSHEET)
    sheet.update_acell("C1", token)
