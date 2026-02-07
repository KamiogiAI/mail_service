from sqlalchemy import Column, Integer, String, DateTime, Enum as SAEnum, ForeignKey, func
from app.core.database import Base


class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True)
    send_type = Column(
        SAEnum("scheduled", "manual", "system", name="send_type"),
        nullable=False,
        comment="送信タイプ",
    )
    status = Column(
        SAEnum("running", "success", "partial_failed", "failed", "stopped", name="delivery_status"),
        nullable=False,
        default="running",
    )
    subject = Column(String(500), nullable=True, comment="メール件名")
    total_count = Column(Integer, nullable=False, default=0, comment="総送信数")
    success_count = Column(Integer, nullable=False, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
