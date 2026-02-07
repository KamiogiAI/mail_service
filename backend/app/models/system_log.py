from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, func
from app.core.database import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(20), nullable=False, index=True, comment="INFO/WARNING/ERROR/CRITICAL")
    event_type = Column(String(100), nullable=False, index=True, comment="イベント種別")
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    member_no_snapshot = Column(String(8), nullable=True, comment="会員番号スナップショット")
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="SET NULL"), nullable=True, index=True)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True, comment="詳細データ")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
