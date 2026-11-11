import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"
PAYPAL_SANDBOX_API = "https://api-m.sandbox.paypal.com"
PAYPAL_LIVE_API = "https://api-m.paypal.com"


def _clean_env(value: str | None, default: str = "") -> str:
    cleaned = (value if value is not None else default).strip().strip('"').strip("'").strip()
    return cleaned


def load_backend_env() -> None:
    load_dotenv(ENV_FILE, override=True)


load_backend_env()


class Settings:
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "fintech_chatbot")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "MyPassword123")
    APP_TITLE: str = os.getenv("APP_TITLE", "Fintech Chatbot API")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")
    PAYPAL_CLIENT_ID: str = "BAAqVxEhZ5fB4Vs9Tfpk90QH9hFA9fK4UqmF1em5dysIyzQ3oCCXxLI4"
    PAYPAL_CLIENT_SECRET: str = "EP2h4OvvEurLnkZ6TBeSnIUznInm1lw_WNsEQ4u-DCSMIoTxgCZd5L5T_SXl35ZZkHVbvx2ugyc6IoAu"
    PAYPAL_MODE: str = "sandbox"
    PAYPAL_BASE_URL: str = PAYPAL_SANDBOX_API
    PAYPAL_WEBHOOK_ID: str = ""
    PAYPAL_RECEIVER_EMAIL: str = "sb-n43onp53750614@personal.example.com"
    PAYPAL_OWNER_TOKEN: str = os.getenv("PAYPAL_OWNER_TOKEN", "").strip()
    PAYPAL_BUSINESS_COUNTRY: str = os.getenv("PAYPAL_BUSINESS_COUNTRY", "").strip().upper()
    PAYPAL_LIVE_PAYOUTS_ENABLED: bool = str(os.getenv("PAYPAL_LIVE_PAYOUTS_ENABLED", "false")).strip().lower() == "true"
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://0.0.0.0:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175,http://localhost:5176,http://127.0.0.1:5176,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if origin.strip()
    ]
    CORS_ORIGIN_REGEX: str = os.getenv(
        "CORS_ORIGIN_REGEX",
        r"https?://([A-Za-z0-9-]+\.)*(localhost|127\.0\.0\.1|0\.0\.0\.0|daytona\.[A-Za-z0-9.-]+)(:\d+)?",
    )

    def paypal_credentials_configured(self) -> bool:
        return bool(self.PAYPAL_CLIENT_ID and self.PAYPAL_CLIENT_SECRET)

    def reload_paypal(self) -> None:
        load_backend_env()
        self.PAYPAL_CLIENT_ID = _clean_env(os.getenv("PAYPAL_CLIENT_ID"))
        self.PAYPAL_CLIENT_SECRET = _clean_env(os.getenv("PAYPAL_CLIENT_SECRET"))
        mode = _clean_env(os.getenv("PAYPAL_MODE"), "sandbox").lower()
        self.PAYPAL_MODE = mode if mode in {"sandbox", "live"} else "sandbox"
        self.PAYPAL_BASE_URL = PAYPAL_SANDBOX_API if self.PAYPAL_MODE == "sandbox" else PAYPAL_LIVE_API
        self.PAYPAL_WEBHOOK_ID = _clean_env(os.getenv("PAYPAL_WEBHOOK_ID"))
        self.PAYPAL_RECEIVER_EMAIL = _clean_env(
            os.getenv("PAYPAL_RECEIVER_EMAIL")
            or os.getenv("PAYPAL_MENTOR_EMAIL")
            or os.getenv("PAYPAL_RECIPIENT_EMAIL")
            or "deepsbiswa@yahoo.com"
        )
        self.PAYPAL_OWNER_TOKEN = _clean_env(os.getenv("PAYPAL_OWNER_TOKEN") or os.getenv("PAYPAL_OWNER_API_KEY"))
        self.PAYPAL_BUSINESS_COUNTRY = _clean_env(os.getenv("PAYPAL_BUSINESS_COUNTRY") or os.getenv("PAYPAL_ACCOUNT_COUNTRY")).upper()
        self.PAYPAL_LIVE_PAYOUTS_ENABLED = str(
            os.getenv("PAYPAL_LIVE_PAYOUTS_ENABLED", "false")
        ).strip().lower() == "true"


settings = Settings()
settings.reload_paypal()
