from sqlalchemy import Column, Integer, String, Text, SmallInteger, DateTime, ForeignKey, func
from app.core.database import Base


class ReportDeliveryItem(Base):
    __tablename__ = "report_delivery_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_delivery_id = Column(Integer, ForeignKey("report_deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    admin_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(SmallInteger, nullable=False, default=0, comment="0=未送信, 1=送信中, 2=送信完了, 3=送信失敗")
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
