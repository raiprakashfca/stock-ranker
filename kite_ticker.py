# kite_ticker.py
"""
One-shot updater for LiveLTPStore.

Reads symbols from LiveLTPStore (col A, row 2+),
fetches LTP + % change using kite.ltp,
and writes back [Symbol, LTP, % Change].

Schedule this script via cron / GitHub Actions.
"""

import logging
from typing import Dict, List

from kiteconnect import KiteConnect

from utils.google_client import get_gspread_client
from utils.token_store import read_token_row


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("kite_ticker")


def _get_kite() -> KiteConnect:
    tr = read_token_row()
    kite = KiteConnect(api_key=tr.api_key)
    kite.set_access_token(tr.access_token)
    return kite


def _load_symbols() -> List[str]:
    client = get_gspread_client()
    ws = client.open("LiveLTPStore").sheet1
    values = ws.get_all_values()
    symbols: List[str] = []
    for row in values[1:]:  # skip header
        if not row:
            continue
        sym = (row[0] or "").strip().upper()
        if sym:
            symbols.append(sym)
    return symbols


def _fetch_ltp(kite: KiteConnect, symbols: List[str]) -> Dict[str, dict]:
    if not symbols:
        return {}
    keys = [f"NSE:{s}" for s in symbols]
    return kite.ltp(keys)


def _update_sheet(ltp_resp: Dict[str, dict]) -> None:
    client = get_gspread_client()
    ws = client.open("LiveLTPStore").sheet1

    rows = []
    for key, info in ltp_resp.items():
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

    payload = [["Symbol", "LTP", "% Change"]] + rows
    ws.update("A1", payload)
    logger.info("Updated LiveLTPStore for %d symbols", len(rows))


def main():
    logger.info("Starting LiveLTPStore updater...")
    symbols = _load_symbols()
    if not symbols:
        logger.warning("No symbols found in LiveLTPStore.")
        return

    kite = _get_kite()
    data = _fetch_ltp(kite, symbols)
    if not data:
        logger.error("No LTP data returned from Zerodha.")
        return

    _update_sheet(data)
    logger.info("Done.")


if __name__ == "__main__":
    main()
