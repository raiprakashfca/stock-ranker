# tmv_updater.py
import os
import logging
from datetime import datetime
from typing import List

import pandas as pd
import pytz

from utils.google_client import get_gspread_client
from utils.indicators import calculate_scores
from fetch_ohlc import fetch_ohlc_data

IST = pytz.timezone("Asia/Kolkata")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_updater")

BACKGROUND_SHEET_KEY = os.getenv("BACKGROUND_SHEET_KEY", "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI")
WATCHLIST_WS = os.getenv("WATCHLIST_WORKSHEET", "Watchlist")
LIVESCORE_WS = os.getenv("LIVESCORE_WORKSHEET", "LiveScores")

def load_watchlist() -> List[str]:
    gc = get_gspread_client()
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(WATCHLIST_WS)
    values = ws.col_values(1)  # Column A
    syms = []
    for v in values[1:]:  # skip header
        v = (v or "").strip().upper().replace("-", "_")
        if v:
            syms.append(v)
    return sorted(list(dict.fromkeys(syms)))

def compute_table(symbols: List[str]) -> pd.DataFrame:
    as_of = datetime.now(IST).replace(microsecond=0).isoformat()
    rows = []

    for sym in symbols:
        try:
            df = fetch_ohlc_data(sym, interval="15minute", days=10)
            if df is None or df.empty:
                logger.warning("No OHLC for %s", sym)
                continue

            # fetch_ohlc_data returns indexed dataframe; convert to expected columns
            df2 = df.reset_index().rename(columns={"index": "date"})
            if "date" not in df2.columns and "date" in df.columns:
                df2["date"] = df["date"]

            scores = calculate_scores(df2)
            if not scores or "TMV Score" not in scores:
                logger.warning("No scores for %s", sym)
                continue

            row = {"Symbol": sym, "AsOf": as_of}
            row.update(scores)
            rows.append(row)

        except Exception as e:
            logger.exception("Error scoring %s: %s", sym, e)

    return pd.DataFrame(rows)

def write_livescores(df: pd.DataFrame) -> None:
    gc = get_gspread_client()
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(LIVESCORE_WS)

    if df.empty:
        logger.error("No rows to write.")
        return

    # Stable column order
    preferred = ["Symbol", "TMV Score", "Confidence", "Trend Direction", "Regime", "Reversal Probability", "AsOf", "CandleTime"]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[cols].copy()

    # Write
    ws.clear()
    ws.update("A1", [df.columns.tolist()] + df.astype(str).values.tolist())

    # Watchdog timestamp (H1)
    watchdog = datetime.now(IST).replace(microsecond=0).isoformat()
    ws.update("H1", [[watchdog]])

    logger.info("Wrote %d rows to %s/%s", len(df), BACKGROUND_SHEET_KEY, LIVESCORE_WS)

def main():
    symbols = load_watchlist()
    if not symbols:
        logger.error("Watchlist empty.")
        return

    df = compute_table(symbols)
    if df.empty:
        logger.error("Computed table empty.")
        return

    write_livescores(df)

if __name__ == "__main__":
    main()
