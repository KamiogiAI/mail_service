from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, Time, Enum as SAEnum, JSON, func
from app.core.database import Base


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, comment="プラン名")
    description = Column(Text, nullable=True, comment="プラン説明")
    is_active = Column(Boolean, nullable=False, default=True)

    # Stripe連携
    stripe_product_id = Column(String(255), nullable=True, unique=True)
    stripe_price_id = Column(String(255), nullable=True, unique=True)
    price = Column(Integer, nullable=False, comment="月額料金 (円)")

    # スケジュール設定
    schedule_type = Column(
        SAEnum("daily", "weekday", "sheets", name="schedule_type"),
        nullable=False,
        default="daily",
        comment="配信タイプ: daily=毎日, weekday=曜日指定, sheets=Sheets日付",
    )
    schedule_weekdays = Column(JSON, nullable=True, comment="曜日指定 (0=月〜6=日)")
    send_time = Column(Time, nullable=False, comment="配信時刻 (JST)")

    # Sheetsカスタム日付
    sheets_id = Column(String(500), nullable=True, comment="Google Sheets ID")

    # GPT設定
    model = Column(String(50), nullable=False, default="gpt-4o-mini", comment="OpenAIモデル名")
    system_prompt = Column(Text, nullable=True, comment="システムプロンプト")
    prompt = Column(Text, nullable=False, comment="ユーザープロンプト (変数含む)")

    # バッチ送信
    batch_send_enabled = Column(Boolean, nullable=False, default=False, comment="まとめて送信")

    # 初月無料
    trial_enabled = Column(Boolean, nullable=False, default=True, comment="初月無料トライアルを有効にする")

    # 削除予約
    pending_delete = Column(Boolean, nullable=False, default=False, comment="削除予約フラグ")

    # 並び順
    sort_order = Column(Integer, nullable=False, default=0, comment="表示順（小さいほど上）")

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
