import gspread
import os
import json
import base64
import logging
from core.config import settings

logger = logging.getLogger(__name__)


def gsheetConnection():
    try:
        if settings.is_vercel:
            cred_base64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
            if not cred_base64:
                raise RuntimeError("GOOGLE_CREDENTIALS_BASE64 env var is not set")
            cred_json = json.loads(base64.b64decode(cred_base64))
            gc = gspread.service_account.from_dict(cred_json)
        else:
            gc = gspread.service_account(filename=settings.CREDENTIALS_FILE)

        if not settings.SPREADSHEET_NAME:
            raise RuntimeError("SPREADSHEET_NAME env var is not set")
        sheet = gc.open(settings.SPREADSHEET_NAME).sheet1
        return sheet
    except Exception as e:
        logger.error(f"Gagal terhubung ke Google Sheet: {e}")
        raise RuntimeError(f"Gagal terhubung ke Google Sheet: {e}") from e
