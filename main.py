from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from core.config import settings
from modules.registration.router import router as registration_router

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.use_neon:
        from core import neon_db
        logger.info("Initializing Neon PostgreSQL database...")
        neon_db.init_db()
        try:
            neon_db.sync_from_gsheets()
        except Exception as e:
            logger.error(f"Initial sync from Google Sheets failed: {e}")
            logger.warning("App will run with existing database data (if any).")
    else:
        from core import sqlite_db
        logger.info("Initializing SQLite database...")
        sqlite_db.init_db()
        try:
            sqlite_db.sync_from_gsheets()
        except Exception as e:
            logger.error(f"Initial sync from Google Sheets failed: {e}")
            logger.warning("App will run with existing SQLite data (if any).")
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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


@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"), media_type="text/html")


@app.get("/styles.css")
def serve_css():
    return FileResponse(os.path.join(BASE_DIR, "styles.css"), media_type="text/css")


@app.get("/app.js")
def serve_js():
    return FileResponse(os.path.join(BASE_DIR, "app.js"), media_type="application/javascript")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=2424, reload=True)
