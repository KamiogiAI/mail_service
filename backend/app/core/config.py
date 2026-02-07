from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """アプリケーション設定"""

    # データベース
    DATABASE_URL: str = "mysql+pymysql://mailuser:mailpassword@db:3306/mail_service?charset=utf8mb4"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # セキュリティ
    AES_KEY: str = ""
    JWT_SECRET: str = "dev-secret-change-me"

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Resend
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@example.com"
    RESEND_WEBHOOK_SECRET: str = ""

    # OpenAI
    OPENAI_API_KEY: str = ""

    # サービス設定
    SITE_URL: str = "http://localhost:8000"
    SITE_NAME: str = "Mail Service"
    ALLOWED_ORIGINS: str = "http://localhost:8000,http://localhost:3000"

    # セッション
    SESSION_TIMEOUT_MINUTES: int = 60

    # スケジューラ
    SCHEDULER_TOKEN: str = ""

    # 環境
    ENV: str = "development"
    DEBUG: bool = True

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
