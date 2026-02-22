"""ユーザーメール履歴モデル

マイページからユーザーが自分に送信されたメールを確認するためのテーブル。
ユーザー×プランごとに最新1件のみ保持する。
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from app.core.database import Base


class UserEmailHistory(Base):
    __tablename__ = "user_email_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="SET NULL"), nullable=True)
    subject = Column(String(500), nullable=False)
    body_html = Column(MEDIUMTEXT, nullable=False)
    sent_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
