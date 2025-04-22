import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="📈 TMV Stock Ranker", layout="wide")

# Function to load background analysis sheet
@st.cache_data(ttl=60)
def load_background_analysis():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        client = gspread.service_account_from_dict(creds_dict)
        sheet = client.open("BackgroundAnalysisStore")
        ws = sheet.worksheet("LiveScores")  # Make sure this name is correct
        df = pd.DataFrame(ws.get_all_records())
        return df
    except Exception as e:
        st.error(f"❌ Failed to load data from Google Sheet: {e}")
        return pd.DataFrame()

# Load data
df = load_background_analysis()

if df.empty:
    st.warning("No data available.")
else:
    # Move LTP and % Change columns next to Symbol
    symbol_col = df.pop("Symbol")
    ltp_col = df.pop("LTP")
    pct_col = df.pop("% Change")
    df.insert(0, "Symbol", symbol_col)
    df.insert(1, "LTP", ltp_col)
    df.insert(2, "% Change", pct_col)

    # Display the data in Streamlit
    st.title("📊 TMV Stock Ranking Dashboard")
    st.dataframe(df, use_container_width=True)
