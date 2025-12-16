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
    "1Cpgj1M_ofN1SqvuqDDHuN7Gy17tfkhy4fCCP8Mx7bRI",
)

WATCHLIST_WS = os.getenv("WATCHLIST_WORKSHEET", "Watchlist")
LIVESCORE_WS = os.getenv("LIVESCORE_WORKSHEET", "LiveScores")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("tmv_updater")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def now_ist() -> datetime:
    return datetime.now(IST).replace(microsecond=0)


def now_ist_iso() -> str:
    return now_ist().isoformat()


# ─────────────────────────────────────────────────────────────
# Load watchlist
# ─────────────────────────────────────────────────────────────
def load_watchlist(gc) -> List[str]:
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(WATCHLIST_WS)
    raw = ws.col_values(1)

    symbols = []
    for s in raw[1:]:  # skip header
        s = (s or "").strip().upper().replace("-", "_")
        if s:
            symbols.append(s)

    symbols = list(dict.fromkeys(symbols))  # dedupe, keep order
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

            # Drop last candle if it looks like a live/incomplete candle
            last_ts = pd.to_datetime(df["date"].iloc[-1], errors="coerce")
            if last_ts is not None:
                age_sec = (now_ist() - last_ts.tz_localize(IST)).total_seconds()
                if age_sec < 60 * 15:
                    df = df.iloc[:-1]

            if len(df) < 60:
                logger.warning("Not enough candles for %s (%d)", sym, len(df))
                continue

            scores = calculate_scores(df)

            if not scores or "TMV Score" not in scores:
                logger.warning("TMV Score missing for %s", sym)
                continue

            rows.append(
                {
                    "Symbol": sym,
                    "TMV Score": scores.get("TMV Score"),
                    "Confidence": scores.get("Confidence"),
                    "Trend Direction": scores.get("Trend Direction"),
                    "Regime": scores.get("Regime"),
                    "Reversal Probability": scores.get("Reversal Probability"),
                    "CandleTime": scores.get("CandleTime"),
                    "AsOf": as_of,
                }
            )

        except Exception:
            logger.exception("Error processing %s", sym)

    df_out = pd.DataFrame(rows)

    if df_out.empty:
        logger.error("No TMV rows generated.")
        return df_out

    df_out.columns = [str(c).strip() for c in df_out.columns]

    if "TMV Score" not in df_out.columns:
        raise RuntimeError("TMV Score column missing AFTER computation")

    logger.info("Computed TMV for %d symbols | AsOf=%s", len(df_out), as_of)
    return df_out


# ─────────────────────────────────────────────────────────────
# Write to Google Sheet (NO CLEAR)
# ─────────────────────────────────────────────────────────────
def write_livescores(gc, df: pd.DataFrame):
    ws = gc.open_by_key(BACKGROUND_SHEET_KEY).worksheet(LIVESCORE_WS)

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

    cols = [c for c in preferred_order if c in df.columns]
    cols += [c for c in df.columns if c not in cols]
    df = df[cols].copy()

    values = [df.columns.tolist()] + df.astype(str).values.tolist()

    ws.update("A1", values)

    # watchdog timestamp
    ws.update("H1", [[now_ist_iso()]])

    logger.info("LiveScores written: %d rows", len(df))


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
def main():
    gc = get_gspread_client()

    symbols = load_watchlist(gc)
    if not symbols:
        logger.error("Watchlist empty. Aborting.")
        return

    df = compute_livescores(symbols)
    if df.empty:
        logger.error("No data to write. Aborting.")
        return

    write_livescores(gc, df)


if __name__ == "__main__":
    main()
