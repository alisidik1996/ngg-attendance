import os
import sys
import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import settings
from modules.registration.router import router as registration_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

lifespan_status = {"init": "not_started", "sync": "not_started", "error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        if settings.use_neon:
            from core import neon_db
            logger.info("Initializing Neon PostgreSQL database...")
            try:
                neon_db.init_db()
                lifespan_status["init"] = "ok"
            except Exception as e:
                lifespan_status["init"] = "failed"
                lifespan_status["error"] = f"init_db: {e}"
                logger.error(f"Neon init_db failed: {e}")
            try:
                count = neon_db.count_participants()
                if count == 0:
                    neon_db.sync_from_gsheets()
                    lifespan_status["sync"] = "ok"
                else:
                    lifespan_status["sync"] = f"skipped_existing_{count}"
                    logger.info(f"Sync skipped, {count} participants already in Neon.")
            except Exception as e:
                lifespan_status["sync"] = "failed"
                lifespan_status["error"] = f"sync: {e}"
                logger.error(f"Initial sync from Google Sheets failed: {e}")
        else:
            from core import sqlite_db
            logger.info("Initializing SQLite database...")
            try:
                sqlite_db.init_db()
                lifespan_status["init"] = "ok"
            except Exception as e:
                lifespan_status["init"] = "failed"
                lifespan_status["error"] = f"sqlite init: {e}"
                logger.error(f"SQLite init failed: {e}")
            try:
                sqlite_db.sync_from_gsheets()
                lifespan_status["sync"] = "ok"
            except Exception as e:
                lifespan_status["sync"] = "failed"
                lifespan_status["error"] = f"sync: {e}"
                logger.error(f"Initial sync from Google Sheets failed: {e}")
    except Exception as e:
        lifespan_status["error"] = f"lifespan: {e}"
        logger.error(f"Lifespan failed: {e}\n{traceback.format_exc()}")
    yield


app = FastAPI(
    title="NGG Attendance API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(registration_router)


@app.get("/health")
def health_check():
    result = {
        "status": "ok",
        "database": "neon" if settings.use_neon else "sqlite",
        "has_database_url": bool(settings.DATABASE_URL),
        "has_gsheets_creds": bool(os.getenv("GOOGLE_CREDENTIALS_BASE64")) or not settings.is_vercel,
        "spreadsheet_name": settings.SPREADSHEET_NAME,
        "lifespan": dict(lifespan_status),
    }
    try:
        if settings.use_neon:
            from core import neon_db
            result["participants"] = neon_db.count_participants()
            result["db_connected"] = True
        else:
            from core import sqlite_db
            conn = sqlite_db.get_db()
            try:
                cur = conn.execute("SELECT COUNT(*) FROM participants")
                result["participants"] = cur.fetchone()[0]
            finally:
                conn.close()
            result["db_connected"] = True
    except Exception as e:
        result["status"] = "error"
        result["db_connected"] = False
        result["db_error"] = str(e)
    return result
