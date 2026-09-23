import logging
import os
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from core.config import settings
from modules.admin.router import router as admin_router
from modules.auth.router import router as auth_router
from modules.registration.router import router as registration_router

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

lifespan_status = {"init": "not_started", "sync": "not_started", "error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    lifespan_status["init"] = "not_started"
    lifespan_status["sync"] = "not_started"
    lifespan_status["error"] = None

    problems = settings.validate()
    for p in problems:
        logger.error("Config invalid: %s", p)
    if problems:
        lifespan_status["error"] = "config: " + "; ".join(problems)

    try:
        from core.db import db
        logger.info("Initializing %s database...", "Neon PostgreSQL" if settings.use_neon else "SQLite")
        migrated = False
        try:
            migrated = db.init_db()
            lifespan_status["init"] = "ok"
        except Exception as e:
            lifespan_status["init"] = "failed"
            if not lifespan_status["error"]:
                lifespan_status["error"] = f"init_db: {e}"
            logger.error("Database init_db failed: %s", e)

        try:
            count = db.count_participants()
            if count == 0 or migrated:
                db.sync_from_gsheets()
                lifespan_status["sync"] = "ok"
            else:
                lifespan_status["sync"] = f"skipped_existing_{count}"
                logger.info("Sync skipped, %d participants already in DB.", count)
        except Exception as e:
            lifespan_status["sync"] = "failed"
            if not lifespan_status["error"]:
                lifespan_status["error"] = f"sync: {e}"
            logger.error("Initial sync from Google Sheets failed: %s", e)
    except Exception as e:
        lifespan_status["error"] = f"lifespan: {e}"
        logger.error("Lifespan failed: %s\n%s", e, traceback.format_exc())
    yield


def create_app(*, serve_static: bool = False, docs_enabled: bool | None = None) -> FastAPI:
    if docs_enabled is None:
        docs_enabled = not settings.is_vercel

    logging.basicConfig(level=logging.INFO)

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            "Unhandled error on %s %s: %s\n%s",
            request.method,
            request.url.path,
            exc,
            traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": "Terjadi kesalahan pada server"},
        )

    app.include_router(auth_router)
    app.include_router(admin_router)
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
            from core.db import db
            result["participants"] = db.count_participants()
            result["db_connected"] = True
        except Exception as e:
            result["status"] = "error"
            result["db_connected"] = False
            result["db_error"] = str(e)
            return JSONResponse(status_code=503, content=result)
        return result

    if serve_static:
        @app.get("/")
        def root():
            return FileResponse(os.path.join(PUBLIC_DIR, "index.html"), media_type="text/html")

        @app.get("/styles.css")
        def serve_css():
            return FileResponse(os.path.join(PUBLIC_DIR, "styles.css"), media_type="text/css")

        @app.get("/app.js")
        def serve_js():
            return FileResponse(os.path.join(PUBLIC_DIR, "app.js"), media_type="application/javascript")

    return app
