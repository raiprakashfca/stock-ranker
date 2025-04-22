from kiteconnect import KiteConnect
import pandas as pd
import datetime

def get_kite(api_key, access_token):
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite

def get_stock_data(kite, symbol, interval, days):
    try:
        to_date = datetime.datetime.now()
        from_date = to_date - datetime.timedelta(days=days)

        ltp_data = kite.ltp(f"NSE:{symbol}")
        instrument_token = ltp_data[f"NSE:{symbol}"]["instrument_token"]

        data = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval=interval
        )
        return pd.DataFrame(data)
    except Exception as e:
        print(f"⚠️ Failed to fetch historical data for {symbol}: {e}")
        return pd.DataFrame()

def update_ltp_sheet(kite, sheet, symbols):
    try:
        ltp_data = kite.ltp([f"NSE:{symbol}" for symbol in symbols])
        rows = []
        for symbol in symbols:
            quote = ltp_data.get(f"NSE:{symbol}")
            if quote:
                ltp = round(quote["last_price"], 2)
                rows.append([symbol, ltp])

        # Update headers and data
        sheet.update(range_name="A1:B1", values=[["Symbol", "LTP"]])
        sheet.update(range_name="A2", values=rows)
        print("✅ LTPs updated to sheet.")
    except Exception as e:
        print(f"⚠️ Could not update LTPs to sheet: {e}")
