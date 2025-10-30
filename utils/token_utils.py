import streamlit as st
import gspread
import json
from google.oauth2.service_account import Credentials

SCOPE = ["https://www.googleapis.com/auth/spreadsheets",
         "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "ZerodhaTokenStore"
WORKSHEET  = "Sheet1"


def get_gsheet_client():
    # Parse the JSON string from secrets
    sa_json = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(sa_json, scopes=SCOPE)
    return gspread.authorize(creds)


def load_credentials_from_gsheet():
    client = get_gsheet_client()
    sheet  = client.open(SHEET_NAME).worksheet(WORKSHEET)
    api_key  = sheet.acell("A1").value
    api_secret = sheet.acell("B1").value
    access_token = sheet.acell("C1").value
    return api_key, api_secret, access_token


def save_token_to_gsheet(token: str):
    client = get_gsheet_client()
    sheet  = client.open(SHEET_NAME).worksheet(WORKSHEET)
    sheet.update_acell("C1", token)
