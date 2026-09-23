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
    LOGIN_RATE_LIMIT: int = int(os.getenv("LOGIN_RATE_LIMIT") or "30")
    LOGIN_RATE_WINDOW_SECONDS: int = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS") or "60")

    @property
    def is_vercel(self) -> bool:
        return os.getenv("VERCEL") == "1"

    @property
    def use_neon(self) -> bool:
        return bool(self.DATABASE_URL)

    def validate(self) -> list:
        problems = []
        if self.SESSION_TTL_HOURS < 1:
            problems.append("SESSION_TTL_HOURS harus >= 1")
        if self.LOGIN_MAX_FAILURES < 1:
            problems.append("LOGIN_MAX_FAILURES harus >= 1")
        if self.LOGIN_LOCK_MINUTES < 1:
            problems.append("LOGIN_LOCK_MINUTES harus >= 1")
        if self.LOGIN_RATE_LIMIT < 1:
            problems.append("LOGIN_RATE_LIMIT harus >= 1")
        if self.is_vercel:
            if not self.DATABASE_URL:
                problems.append("DATABASE_URL wajib di-set di production (Neon)")
            if not os.getenv("GOOGLE_CREDENTIALS_BASE64"):
                problems.append("GOOGLE_CREDENTIALS_BASE64 wajib di-set di Vercel")
            if not self.SPREADSHEET_NAME:
                problems.append("SPREADSHEET_NAME wajib di-set di production")
        return problems


settings = Settings()
