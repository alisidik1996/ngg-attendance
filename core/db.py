from core.config import settings

if settings.use_neon:
    from core import neon_db as db
else:
    from core import sqlite_db as db

__all__ = ["db"]
