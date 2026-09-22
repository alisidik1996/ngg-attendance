import os
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import settings
from modules.registration.router import router as registration_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.use_neon:
        from core import neon_db
        logger.info("Initializing Neon PostgreSQL database...")
        try:
            neon_db.init_db()
        except Exception as e:
            logger.error(f"Neon init_db failed: {e}")
        try:
            neon_db.sync_from_gsheets()
        except Exception as e:
            logger.error(f"Initial sync from Google Sheets failed: {e}")
    else:
        from core import sqlite_db
        logger.info("Initializing SQLite database...")
        sqlite_db.init_db()
        try:
            sqlite_db.sync_from_gsheets()
        except Exception as e:
            logger.error(f"Initial sync from Google Sheets failed: {e}")
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
    db_type = "neon" if settings.use_neon else "sqlite"
    return {"status": "ok", "database": db_type}
