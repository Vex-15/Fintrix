from pydantic_settings import BaseSettings
from typing import Optional
import secrets


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://fintrix:fintrix@localhost:5432/fintrix"

    # LLM
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None

    # AI Guardrails
    auto_resolve_confidence_threshold: float = 0.85
    auto_resolve_max_amount_paise: int = 1_000_000  # ₹10,000
    always_escalate_amount_paise: int = 10_000_000  # ₹1,00,000

    # Hypothesis Engine
    hypothesis_confidence_floor: float = 0.6  # Skip LLM if rule-based confidence >= this

    # Financial Configuration
    expected_mdr_rate: float = 0.02
    expected_gst_rate: float = 0.18
    plausible_mdr_rates: list[float] = [0.018, 0.020, 0.022]

    # Feature gates
    enable_scheduler: bool = False   # Set True to enable cron jobs
    razorpay_live_demo: bool = False  # Set True to enable live Razorpay API calls

    # App
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # JWT Authentication
    jwt_secret_key: str = secrets.token_urlsafe(32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Demo Mode
    demo_mode: bool = False

    # Razorpay
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    razorpay_webhook_secret: Optional[str] = None

    # Scheduler
    scheduler_reconciliation_cron: str = "0 */6 * * *"  # Every 6 hours
    scheduler_razorpay_sync_minutes: int = 15

    # Default admin (created on first startup)
    default_admin_email: str = "admin@fintrix.io"
    default_admin_password: str = "admin123"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    model_config = {"env_file": (".env", "../.env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
