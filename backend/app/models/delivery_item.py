from sqlalchemy import Column, Integer, String, Text, DateTime, SmallInteger, ForeignKey, func
from app.core.database import Base


class DeliveryItem(Base):
    __tablename__ = "delivery_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    member_no_snapshot = Column(String(8), nullable=False, comment="会員番号スナップショット")
    document_key = Column(String(255), nullable=True, comment="外部データドキュメントキー")
    status = Column(SmallInteger, nullable=False, default=0, comment="0=未実行, 1=実行中, 2=完了, 3=エラー")
    retry_count = Column(Integer, nullable=False, default=0)
    resend_message_id = Column(String(255), nullable=True, comment="Resend メッセージID")
    last_error_code = Column(String(50), nullable=True, comment="最終エラーコード")
    last_error_message = Column(Text, nullable=True, comment="最終エラーメッセージ")
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
