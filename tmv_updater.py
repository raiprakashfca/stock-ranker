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

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
IST = pytz.timezone("Asia/Kolkata")

BACKGROUND_SHEET_KEY = os.getenv(
    "BACKGROUND_SHEET_KEY",
    "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI"
)

WATCHLIST_WS = os.getenv("WATCHLIST_WORKSHEET", "Watchlist")
LIVESCORE_WS = os.getenv("LIVESCORE_WORKSHEET", "LiveScores")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("tmv_updater")

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def now_ist_iso() -> str:
    return datetime.now(IST).replace(microsecond=0).isoformat()

# ─────────────────────────────────────────────────────────────
# Load symbols
# ─────────────────────────────────────────────────────────────
def load_watchlist() -> List[str]:
    gc = get_gspread_client()
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(WATCHLIST_WS)

    raw = ws.col_values(1)  # column A
    symbols = []

    for s in raw[1:]:  # skip header
        s = (s or "").strip().upper().replace("-", "_")
        if s:
            symbols.append(s)

    symbols = list(dict.fromkeys(symbols))  # de-dup, preserve order
    logger.info("Loaded %d symbols from watchlist", len(symbols))
    return symbols

# ─────────────────────────────────────────────────────────────
# Compute TMV table
# ─────────────────────────────────────────────────────────────
def compute_livescores(symbols: List[str]) -> pd.DataFrame:
    rows = []
    as_of = now_ist_iso()

    for sym in symbols:
        try:
            ohlc = fetch_ohlc_data(sym, interval="15minute", days=10)

            if ohlc is None or ohlc.empty:
                logger.warning("No OHLC for %s", sym)
                continue

            df = ohlc.reset_index()
            if "date" not in df.columns:
                df.rename(columns={df.columns[0]: "date"}, inplace=True)

            scores = calculate_scores(df)

            if not scores or "TMV Score" not in scores:
                logger.warning("TMV Score missing for %s", sym)
                continue

            row = {
                "Symbol": sym,
                "TMV Score": scores.get("TMV Score"),
                "Confidence": scores.get("Confidence"),
                "Trend Direction": scores.get("Trend Direction"),
                "Regime": scores.get("Regime"),
                "Reversal Probability": scores.get("Reversal Probability"),
                "CandleTime": scores.get("CandleTime"),
                "AsOf": as_of,
            }

            rows.append(row)

        except Exception as e:
            logger.exception("Error processing %s: %s", sym, e)

    df_out = pd.DataFrame(rows)

    if df_out.empty:
        logger.error("No TMV rows generated.")
        return df_out

    # 🔒 HARD GUARANTEE: normalize headers
    df_out.columns = [str(c).strip() for c in df_out.columns]

    # 🔒 HARD GUARANTEE: TMV Score column
    if "TMV Score" not in df_out.columns:
        raise RuntimeError("TMV Score column missing AFTER computation (should never happen)")

    return df_out

# ─────────────────────────────────────────────────────────────
# Write to Google Sheet
# ─────────────────────────────────────────────────────────────
def write_livescores(df: pd.DataFrame):
    gc = get_gspread_client()
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(LIVESCORE_WS)

    # Stable, app-compatible column order
    preferred_order = [
        "Symbol",
        "TMV Score",
        "Confidence",
        "Trend Direction",
        "Regime",
        "Reversal Probability",
        "CandleTime",
        "AsOf",
    ]

    final_cols = [c for c in preferred_order if c in df.columns]
    final_cols += [c for c in df.columns if c not in final_cols]

    df = df[final_cols].copy()

    # Clear & write
    ws.clear()
    ws.update(
        "A1",
        [df.columns.tolist()] + df.astype(str).values.tolist()
    )

    # Watchdog timestamp (used only for visibility)
    ws.update("H1", [[now_ist_iso()]])

    logger.info("LiveScores updated with %d rows", len(df))

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    symbols = load_watchlist()
    if not symbols:
        logger.error("Watchlist empty. Aborting.")
        return

    df = compute_livescores(symbols)
    if df.empty:
        logger.error("No data to write. Aborting.")
        return

    write_livescores(df)

if __name__ == "__main__":
    main()
