import os
import sys
import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse

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
            migrated = False
            try:
                migrated = neon_db.init_db()
                lifespan_status["init"] = "ok"
            except Exception as e:
                lifespan_status["init"] = "failed"
                lifespan_status["error"] = f"init_db: {e}"
                logger.error(f"Neon init_db failed: {e}")
            try:
                count = neon_db.count_participants()
                if count == 0 or migrated:
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
            migrated = False
            try:
                migrated = sqlite_db.init_db()
                lifespan_status["init"] = "ok"
            except Exception as e:
                lifespan_status["init"] = "failed"
                lifespan_status["error"] = f"sqlite init: {e}"
                logger.error(f"SQLite init failed: {e}")
            try:
                count = sqlite_db.count_participants()
                if count == 0 or migrated:
                    sqlite_db.sync_from_gsheets()
                    lifespan_status["sync"] = "ok"
                else:
                    lifespan_status["sync"] = f"skipped_existing_{count}"
                    logger.info(f"Sync skipped, {count} participants already in SQLite.")
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

app.include_router(registration_router)


@app.get("/health")
def health_check():
    result = {
        "status": "ok",
        "database": "neon" if settings.use_neon else "sqlite",
        "has_database_url": bool(settings.DATABASE_URL),
        "has_gsheets_creds": bool(os.getenv("GOOGLE_CREDENTIALS_BASE64")) or not settings.is_vercel,
        "lifespan": dict(lifespan_status),
    }
    try:
        if settings.use_neon:
            from core import neon_db
            result["participants"] = neon_db.count_participants()
            result["db_connected"] = True
        else:
            from core import sqlite_db
            result["participants"] = sqlite_db.count_participants()
            result["db_connected"] = True
    except Exception as e:
        result["status"] = "error"
        result["db_connected"] = False
        result["db_error"] = str(e)
        return JSONResponse(status_code=503, content=result)
    return result
