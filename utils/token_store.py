# utils/token_store.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from kiteconnect import KiteConnect

from .google_client import get_gspread_client


IST = timezone(timedelta(hours=5, minutes=30))

SHEET_NAME = "ZerodhaTokenStore"
WORKSHEET = "Sheet1"


@dataclass
class TokenRow:
    api_key: str
    api_secret: str
    access_token: str
    expires_at: Optional[datetime]
    updated_at: Optional[datetime]


def _get_token_sheet():
    client = get_gspread_client()
    return client.open(SHEET_NAME).worksheet(WORKSHEET)


def read_token_row() -> TokenRow:
    ws = _get_token_sheet()
    row = ws.row_values(1) + ["", "", "", "", ""]
    api_key = (row[0] or "").strip()
    api_secret = (row[1] or "").strip()
    access_token = (row[2] or "").strip()
    expires_at_raw = (row[3] or "").strip()
    updated_at_raw = (row[4] or "").strip()

    expires_at = None
    updated_at = None
    try:
        if expires_at_raw:
            expires_at = datetime.fromisoformat(expires_at_raw)
        if updated_at_raw:
            updated_at = datetime.fromisoformat(updated_at_raw)
    except Exception:
        # ignore bad timestamps; treat as None
        pass

    if not api_key or not api_secret:
        raise RuntimeError("ZerodhaTokenStore missing API key/secret in A1/B1")

    return TokenRow(
        api_key=api_key,
        api_secret=api_secret,
        access_token=access_token,
        expires_at=expires_at,
        updated_at=updated_at,
    )


def write_access_token(access_token: str, ttl_hours: int = 24) -> None:
    ws = _get_token_sheet()
    now = datetime.now(IST)
    expires_at = now + timedelta(hours=ttl_hours - 0.25)
    ws.update("C1", [[access_token]])
    ws.update("D1", [[expires_at.isoformat()]])
    ws.update("E1", [[now.isoformat()]])


def get_kite(validate: bool = True) -> KiteConnect:
    """
    Returns a KiteConnect instance using the stored API key + access token.

    If validate=True, calls kite.profile() once to ensure token is still valid.
    """
    tr = read_token_row()
    kite = KiteConnect(api_key=tr.api_key)
    if not tr.access_token:
        raise RuntimeError("ZerodhaTokenStore C1 is empty (no access_token).")
    kite.set_access_token(tr.access_token)

    if validate:
        # simple ping
        kite.profile()
    return kite
