# kite_ticker.py (cron-friendly version)
#
# Purpose:
#   - Read the watchlist from LiveLTPStore (column A, rows 2+).
#   - Fetch live LTP + % change using Zerodha HTTP APIs (no WebSocket).
#   - Write back to LiveLTPStore as:
#       A: Symbol, B: LTP, C: % Change
#
# Usage:
#   - Configure env:
#       GOOGLE_SERVICE_ACCOUNT_JSON  = JSON string of service account
#       (or GSPREAD_CREDENTIALS_JSON as a fallback)
#   - Ensure ZerodhaTokenStore (Sheet1) row 1 = [API Key, API Secret, Access Token, ...]
#   - Schedule with cron / GitHub Actions every 1–5 minutes.

import os
import json
import logging
from typing import Dict, List

import gspread
from google.oauth2.service_account import Credentials
from kiteconnect import KiteConnect
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("kite_ticker")

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _load_service_account_creds() -> Credentials:
    """
    Load Google service-account credentials from env.
    Tries GOOGLE_SERVICE_ACCOUNT_JSON, then GSPREAD_CREDENTIALS_JSON.
    """
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.environ.get(
        "GSPREAD_CREDENTIALS_JSON"
    )
    if not raw:
        raise RuntimeError(
            "Missing GOOGLE_SERVICE_ACCOUNT_JSON / GSPREAD_CREDENTIALS_JSON in environment."
        )

    try:
        sa_json = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid service-account JSON in env: {e}") from e

    return Credentials.from_service_account_info(sa_json, scopes=SCOPE)


def _gspread_client() -> gspread.Client:
    creds = _load_service_account_creds()
    return gspread.authorize(creds)


def _load_zerodha_credentials(gc: gspread.Client):
    """
    Read Zerodha API key/secret/access_token from ZerodhaTokenStore Sheet1, row 1.
    Assumes layout: A1=API Key, B1=API Secret, C1=Access Token, D1=Expiry (optional).
    """
    ws = gc.open("ZerodhaTokenStore").worksheet("Sheet1")
    row = ws.row_values(1)
    if len(row) < 3:
        raise RuntimeError(
            "ZerodhaTokenStore Sheet1 row 1 does not contain [API Key, API Secret, Access Token]."
        )
    api_key, api_secret, access_token = row[:3]
    return api_key.strip(), api_secret.strip(), access_token.strip()


def _load_symbols(gc: gspread.Client) -> List[str]:
    """
    Load watchlist symbols from LiveLTPStore Sheet1, column A, rows 2+.
    """
    ws = gc.open("LiveLTPStore").sheet1
    values = ws.get_all_values()
    symbols = []
    # Skip header row (index 0)
    for row in values[1:]:
        if not row:
            continue
        sym = (row[0] or "").strip().upper()
        if sym:
            symbols.append(sym)
    return symbols


def _fetch_ltp_batch(kite: KiteConnect, symbols: List[str]) -> Dict[str, dict]:
    if not symbols:
        return {}

    # Build NSE:SYMBOL keys
    keys = [f"NSE:{s}" for s in symbols]
    try:
        data = kite.ltp(keys)
        return data or {}
    except Exception as e:
        logger.error(f"Failed to fetch LTP from Zerodha: {e}")
        return {}


def _update_live_ltp_store(gc: gspread.Client, ltp_resp: Dict[str, dict]):
    """
    Write header + rows back to LiveLTPStore.
    Columns:
      A: Symbol
      B: LTP
      C: % Change
    """
    ws = gc.open("LiveLTPStore").sheet1

    rows = []
    for key, info in ltp_resp.items():
        # key is like "NSE:RELIANCE"
        try:
            _, symbol = key.split(":", 1)
        except ValueError:
            continue

        last_price = info.get("last_price")
        ohlc = info.get("ohlc") or {}
        close = ohlc.get("close") or 0.0

        if last_price is None:
            continue

        if close:
            pct = (last_price - close) / close * 100.0
        else:
            pct = 0.0

        rows.append(
            [
                symbol,
                f"{last_price:.2f}",
                f"{pct:.2f}%",
            ]
        )

    # Sort by % change descending, if you like
    # rows.sort(key=lambda r: float(r[2].rstrip('%')), reverse=True)

    # Write header + rows in a single update
    payload = [["Symbol", "LTP", "% Change"]] + rows
    ws.update("A1", payload)
    logger.info("✅ LiveLTPStore updated with %d symbols", len(rows))


def main():
    logger.info("🚀 Starting one-shot LiveLTPStore updater...")
    try:
        gc = _gspread_client()
        api_key, api_secret, access_token = _load_zerodha_credentials(gc)
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)

        symbols = _load_symbols(gc)
        if not symbols:
            logger.warning("No symbols found in LiveLTPStore. Nothing to do.")
            return

        logger.info("Found %d symbols in LiveLTPStore.", len(symbols))
        ltp_resp = _fetch_ltp_batch(kite, symbols)
        if not ltp_resp:
            logger.error("No LTP data returned from Zerodha. Aborting.")
            return

        _update_live_ltp_store(gc, ltp_resp)
        logger.info("✅ Done.")
    except Exception as e:
        logger.exception("❌ Fatal error in kite_ticker updater: %s", e)
        raise


if __name__ == "__main__":
    main()
