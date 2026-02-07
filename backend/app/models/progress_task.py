from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, ForeignKey, UniqueConstraint, func
from app.core.database import Base


class ProgressTask(Base):
    __tablename__ = "progress_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    document_key = Column(String(255), nullable=True, comment="外部データドキュメントキー")
    status = Column(SmallInteger, nullable=False, default=0, comment="0=未実行, 1=実行中, 2=完了, 3=エラー")
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("delivery_id", "user_id", "document_key", name="uq_delivery_user_doc"),
    )
