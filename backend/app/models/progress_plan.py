from sqlalchemy import Column, Integer, String, Date, SmallInteger, DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint, func
from app.core.database import Base


class ProgressPlan(Base):
    __tablename__ = "progress_plan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, comment="配信日 (JST)")
    send_type = Column(
        SAEnum("scheduled", "manual", name="progress_send_type"),
        nullable=False,
    )
    delivery_id = Column(Integer, ForeignKey("deliveries.id", ondelete="SET NULL"), nullable=True)
    status = Column(SmallInteger, nullable=False, default=0, comment="0=未実行, 1=実行中, 2=完了, 3=エラー")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("plan_id", "date", "send_type", "delivery_id", name="uq_plan_date_type_delivery"),
    )
