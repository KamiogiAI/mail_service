from sqlalchemy import Column, Integer, String, Date, SmallInteger, DateTime, func
from app.core.database import Base


class ReportDelivery(Base):
    __tablename__ = "report_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(Date, nullable=False, unique=True, comment="レポート対象日")
    status = Column(SmallInteger, nullable=False, default=0, comment="0=未送信, 1=送信中, 2=送信完了, 3=送信失敗")
    total_admins = Column(Integer, nullable=False, default=0, comment="送信対象管理者数")
    success_count = Column(Integer, nullable=False, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
