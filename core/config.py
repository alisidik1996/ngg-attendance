import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PROJECT_NAME: str = "Momaz Next-Gen Grow (Attendance System)"
    SPREADSHEET_NAME: str = os.getenv("SPREADSHEET_NAME")
    CREDENTIALS_FILE: str = os.getenv("CREDENTIALS_FILE")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    @property
    def is_vercel(self) -> bool:
        return os.getenv("VERCEL") == "1"

    @property
    def use_neon(self) -> bool:
        return bool(self.DATABASE_URL)


settings = Settings()
