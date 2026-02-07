from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, func
from app.core.database import Base


class ServiceSetting(Base):
    __tablename__ = "service_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # サービス基本情報
    site_name = Column(String(255), nullable=False, default="Mail Service")
    site_url = Column(String(500), nullable=False, default="http://localhost:8000")
    from_email = Column(String(255), nullable=False, default="noreply@example.com")

    # 暗号化されたAPIキー
    openai_api_key_enc = Column(Text, nullable=True, comment="OpenAI APIキー (暗号化)")
    resend_api_key_enc = Column(Text, nullable=True, comment="Resend APIキー (暗号化)")
    stripe_secret_key_enc = Column(Text, nullable=True, comment="Stripe Secret Key (暗号化)")
    stripe_publishable_key = Column(String(255), nullable=True, comment="Stripe Publishable Key (公開)")
    stripe_webhook_secret_enc = Column(Text, nullable=True, comment="Stripe Webhook Secret (暗号化)")
    resend_webhook_secret_enc = Column(Text, nullable=True, comment="Resend Webhook Secret (暗号化)")

    # Firebase SA Key (グローバル)
    firebase_key_json_enc = Column(Text, nullable=True, comment="Firebase SA JSON (暗号化)")
    firebase_client_email = Column(String(255), nullable=True, comment="Firebase client_email (表示用)")

    # Resend Webhook ON/OFF
    resend_webhook_enabled = Column(Boolean, nullable=False, default=False, comment="Resend Webhook有効化")

    # 複数プラン加入制御
    allow_multiple_plans = Column(Boolean, nullable=False, default=False, comment="複数プラン同時加入許可")

    # 静的ページ (Markdown)
    terms_md = Column(Text, nullable=True, comment="利用規約")
    company_md = Column(Text, nullable=True, comment="運営会社情報")
    cancel_md = Column(Text, nullable=True, comment="解約ポリシー")
    tokusho_md = Column(Text, nullable=True, comment="特定商取引法に基づく表記")

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
