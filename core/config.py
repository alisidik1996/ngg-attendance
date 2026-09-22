import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME: str = "Momaz Next-Gen Grow (Attendance System)"
    SPREADSHEET_NAME: str = os.getenv("SPREADSHEET_NAME") or ""
    CREDENTIALS_FILE: str = os.getenv("CREDENTIALS_FILE") or ""
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    SESSION_TTL_HOURS: int = int(os.getenv("SESSION_TTL_HOURS") or "12")
    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME") or "ngg_session"
    LOGIN_MAX_FAILURES: int = int(os.getenv("LOGIN_MAX_FAILURES") or "5")
    LOGIN_LOCK_MINUTES: int = int(os.getenv("LOGIN_LOCK_MINUTES") or "15")

    @property
    def is_vercel(self) -> bool:
        return os.getenv("VERCEL") == "1"

    @property
    def use_neon(self) -> bool:
        return bool(self.DATABASE_URL)


settings = Settings()
