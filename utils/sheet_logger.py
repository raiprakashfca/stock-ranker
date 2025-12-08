# utils/sheet_logger.py

import logging
from typing import Optional

import pandas as pd

try:
    import streamlit as st  # type: ignore
except ImportError:
    st = None

from .google_client import get_gspread_client


def log_to_google_sheets(
    workbook: str,
    sheet_name: str,
    df: pd.DataFrame,
    clear: bool = True,
    max_rows: Optional[int] = None,
) -> None:
    """
    Write a DataFrame to a Google Sheet.

    - workbook: Google Sheet name (e.g., "Stock Rankings")
    - sheet_name: Worksheet name (tab)
    - clear: whether to clear the sheet before writing
    - max_rows: optional cap on number of rows (for huge logs)
    """
    if not isinstance(df, pd.DataFrame):
        if st:
            st.warning("🛑 Sheet log failed: Provided data is not a DataFrame")
        logging.warning("log_to_google_sheets called with non-DataFrame.")
        return

    try:
        df = df.round(2)
        if max_rows is not None:
            df = df.head(max_rows)

        client = get_gspread_client()
        sheet = client.open(workbook).worksheet(sheet_name)

        if clear:
            sheet.clear()

        data = [df.columns.tolist()] + df.values.tolist()
        sheet.update("A1", data)
    except Exception as e:
        msg = f"⚠️ Could not update Google Sheet: {e}"
        logging.warning(msg)
        if st:
            st.warning(msg)
