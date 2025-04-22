
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="📊 TMV Scoreboard", layout="wide")

# Load credentials and connect to Google Sheets
def get_worksheet(sheet_name: str):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    credentials_dict = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(credentials_dict, scopes=scope)
    gc = gspread.authorize(credentials)
    sheet = gc.open(sheet_name)
    return sheet

@st.cache_data(ttl=60)
def load_background_analysis():
    sheet = get_worksheet("BackgroundAnalysisStore")
    ws = sheet.sheet1
    df = pd.DataFrame(ws.get_all_records())
    return df

# Main app
st.title("📊 Multi-Timeframe Stock Ranking Dashboard")

df = load_background_analysis()

if df.empty:
    st.warning("No data found.")
else:
    # Reorder columns
    desired_order = ["Symbol", "LTP", "% Change"] + [col for col in df.columns if col not in ["Symbol", "LTP", "% Change"]]
    df = df[desired_order]

    # Styling
    def highlight_change(val):
        try:
            val = float(val)
            color = 'green' if val > 0 else 'red'
            return f'color: {color}'
        except:
            return ''

    st.dataframe(
        df.style
        .applymap(highlight_change, subset=["% Change"])
        .format({"LTP": "{:.2f}", "% Change": "{:.2f}"}),
        use_container_width=True
    )
