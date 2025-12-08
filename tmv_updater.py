# tmv_updater.py
"""
One-shot TMV updater.

- Reads list of symbols from BackgroundAnalysisStore → Watchlist.
- Fetches OHLC data.
- Computes TMV scores.
- Adds IST timestamp to each row as `AsOf`.
- Logs results back to BackgroundAnalysisStore → LiveScores.

Scheduled via cron / GitHub Actions.
"""

import logging
from datetime import datetime
from typing import List

import pandas as pd
import pytz

from utils.google_client import get_gspread_client
from utils.ohlc import fetch_ohlc
from utils.indicators import calculate_scores
from utils.sheet_logger import log_to_google_sheets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tmv_updater")

IST = pytz.timezone("Asia/Kolkata")

WATCHLIST_WORKBOOK = "BackgroundAnalysisStore"
WATCHLIST_SHEET = "Watchlist"
OUTPUT_WORKBOOK = "BackgroundAnalysisStore"
OUTPUT_SHEET = "LiveScores"


def load_watchlist_symbols() -> List[str]:
    client = get_gspread_client()
    ws = client.open(WATCHLIST_WORKBOOK).worksheet(WATCHLIST_SHEET)
    values = ws.get_all_values()

    symbols: List[str] = []
    for row in values[1:]:
        if not row:
            continue
        sym = (row[0] or "").strip().upper()
        if sym:
            symbols.append(sym)

    return symbols


def compute_tmv_table(symbols: List[str]) -> pd.DataFrame:
    rows = []
    as_of = datetime.now(IST).replace(microsecond=0).isoformat()

    for sym in symbols:
        try:
            df_ohlc = fetch_ohlc(sym, interval="15minute", days=7)
            if df_ohlc.empty:
                logger.warning("No OHLC for %s", sym)
                continue

            scores = calculate_scores(df_ohlc)
            if not scores:
                logger.warning("No TMV scores for %s", sym)
                continue

            row = {"Symbol": sym}
            row.update(scores)
            row["AsOf"] = as_of  # IST timestamp added to every row

            rows.append(row)

        except Exception as e:
            logger.exception("Error computing TMV for %s: %s", sym, e)

    return pd.DataFrame(rows)


def main():
    logger.info("Starting TMV updater...")

    symbols = load_watchlist_symbols()
    if not symbols:
        logger.warning("TMV updater found no symbols in watchlist.")
        return

    df = compute_tmv_table(symbols)
    if df.empty:
        logger.warning("TMV updater produced empty table.")
        return

    log_to_google_sheets(
        workbook=OUTPUT_WORKBOOK,
        sheet_name=OUTPUT_SHEET,
        df=df,
        clear=True,
    )

    logger.info("TMV updater completed with %d rows.", len(df))


if __name__ == "__main__":
    main()
