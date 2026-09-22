import gspread
import os
import json
import base64
import logging
from core.config import settings

logger = logging.getLogger(__name__)

GSCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def gsheetConnection():
    try:
        if settings.is_vercel:
            cred_base64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
            if not cred_base64:
                raise RuntimeError("GOOGLE_CREDENTIALS_BASE64 env var is not set")
            cred_json = json.loads(base64.b64decode(cred_base64))
            gc = gspread.service_account_from_dict(cred_json, scopes=GSCOPES)
        else:
            if not settings.CREDENTIALS_FILE:
                raise RuntimeError("CREDENTIALS_FILE env var is not set")
            gc = gspread.service_account(filename=settings.CREDENTIALS_FILE, scopes=GSCOPES)

        if not settings.SPREADSHEET_NAME:
            raise RuntimeError("SPREADSHEET_NAME env var is not set")
        sheet = gc.open(settings.SPREADSHEET_NAME).sheet1
        return sheet
    except Exception as e:
        logger.error(f"Gagal terhubung ke Google Sheet: {e}")
        raise RuntimeError(f"Gagal terhubung ke Google Sheet: {e}") from e


def push_status_to_gsheets(no_order: str, status_key: str, waktu_key: str, participant: dict) -> bool:
    from gspread.cell import Cell

    try:
        sheet = gsheetConnection()
        data = sheet.get_all_records()
        target = no_order.strip()

        for idx, row in enumerate(data, start=2):
            if str(row.get("order_number", "")).strip() != target:
                continue

            headers = sheet.row_values(1)
            if status_key not in headers or waktu_key not in headers:
                logger.error(
                    f"Column '{status_key}'/'{waktu_key}' not found in Google Sheets header."
                )
                return False

            status_col = headers.index(status_key) + 1
            waktu_col = headers.index(waktu_key) + 1
            sheet.update_cells([
                Cell(row=idx, col=status_col, value=participant.get(status_key) or ""),
                Cell(row=idx, col=waktu_col, value=participant.get(waktu_key) or ""),
            ])
            logger.info(f"Pushed {status_key} for {no_order} to Google Sheets.")
            return True

        logger.warning(f"Order {no_order} not found in Google Sheets.")
        return False
    except Exception as e:
        logger.error(f"Failed to push {status_key} for {no_order} to Google Sheets: {e}")
        return False
