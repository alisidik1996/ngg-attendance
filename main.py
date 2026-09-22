from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
from core.config import settings
from modules.registration.router import router as registration_router
from modules.auth.router import router as auth_router
from modules.admin.router import router as admin_router

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
PUBLIC_DIR = os.path.join(BASE_DIR, "public")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.auth import ensure_bootstrap_admin

    if settings.use_neon:
        from core import neon_db
        logger.info("Initializing Neon PostgreSQL database...")
        migrated = False
        try:
            migrated = neon_db.init_db()
        except Exception as e:
            logger.error(f"Neon init failed: {e}")
        ensure_bootstrap_admin()
        try:
            count = neon_db.count_participants()
            if count == 0 or migrated:
                neon_db.sync_from_gsheets()
                if migrated:
                    logger.info("Backfill after nama_lengkap_ayah migration complete.")
            else:
                logger.info(f"Sync skipped, {count} participants already in Neon.")
        except Exception as e:
            logger.error(f"Initial sync from Google Sheets failed: {e}")
            logger.warning("App will run with existing database data (if any).")
    else:
        from core import sqlite_db
        logger.info("Initializing SQLite database...")
        migrated = False
        try:
            migrated = sqlite_db.init_db()
        except Exception as e:
            logger.error(f"SQLite init failed: {e}")
        ensure_bootstrap_admin()
        try:
            count = sqlite_db.count_participants()
            if count == 0 or migrated:
                sqlite_db.sync_from_gsheets()
                if migrated:
                    logger.info("Backfill after nama_lengkap_ayah migration complete.")
            else:
                logger.info(f"Sync skipped, {count} participants already in SQLite.")
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

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(registration_router)


@app.get("/health")
def health_check():
    db_type = "neon" if settings.use_neon else "sqlite"
    try:
        if settings.use_neon:
            from core import neon_db
            count = neon_db.count_participants()
        else:
            from core import sqlite_db
            count = sqlite_db.count_participants()
        return {"status": "ok", "database": db_type, "participants": count}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": db_type, "detail": str(e)},
        )


@app.get("/")
def root():
    return FileResponse(os.path.join(PUBLIC_DIR, "index.html"), media_type="text/html")


@app.get("/styles.css")
def serve_css():
    return FileResponse(os.path.join(PUBLIC_DIR, "styles.css"), media_type="text/css")


@app.get("/app.js")
def serve_js():
    return FileResponse(os.path.join(PUBLIC_DIR, "app.js"), media_type="application/javascript")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=2424, reload=True)
