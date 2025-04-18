import pandas as pd
import datetime
from kiteconnect import KiteConnect
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import streamlit as st
from urllib.parse import urlencode

def get_kite():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["gspread_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    sheet = client.open("ZerodhaTokenStore")
    worksheet = sheet.sheet1
    tokens = worksheet.row_values(1)

    if len(tokens) < 3:
        st.warning("🔐 API credentials not found in 'ZerodhaTokenStore'. Please generate them below.")

        api_key_input = st.text_input("Enter your Zerodha API Key")
        api_secret_input = st.text_input("Enter your Zerodha API Secret")

        if api_key_input and api_secret_input:
            kite = KiteConnect(api_key=api_key_input)
            redirect_url = "https://stock-ranker.streamlit.app/"  # Replace with your actual Streamlit URL
            login_url = kite.login_url()
            st.markdown(f"[🔑 Click here to generate Access Token]({login_url})")

            request_token = st.text_input("Paste your request_token here")
            if request_token:
                try:
                    data = kite.generate_session(request_token, api_secret=api_secret_input)
                    access_token = data["access_token"]

                    # Save back to Google Sheet
                    worksheet.update("A1", [[api_key_input, api_secret_input, access_token]])
                    st.success("✅ Access token generated and saved successfully. Please refresh the app.")
                    st.stop()
                except Exception as e:
                    st.error(f"❌ Failed to generate session: {e}")
                    st.stop()
        else:
            st.stop()

    api_key, api_secret, access_token = tokens[0], tokens[1], tokens[2]

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

def get_instrument_token(kite, tradingsymbol):
    try:
        instruments = kite.instruments(exchange="NSE")
        for instrument in instruments:
            if instrument["tradingsymbol"] == tradingsymbol:
                return instrument["instrument_token"]
    except Exception as e:
        st.error(f"⚠️ Error fetching instruments: {e}")
    raise ValueError(f"Instrument token not found for {tradingsymbol}")

def get_stock_data(kite, symbol, interval, days):
    try:
        token = get_instrument_token(kite, symbol)
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=days)
        data = kite.historical_data(token, start_date, end_date, interval)
        df = pd.DataFrame(data)
        df.set_index("date", inplace=True)
        return df
    except Exception as e:
        st.error(f"❌ Failed to fetch data for {symbol}: {e}")
        return pd.DataFrame()
