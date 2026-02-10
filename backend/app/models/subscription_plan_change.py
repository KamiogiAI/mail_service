from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from app.core.database import Base


class SubscriptionPlanChange(Base):
    __tablename__ = "subscription_plan_changes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    old_plan_id = Column(Integer, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    new_plan_id = Column(Integer, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    change_type = Column(String(20), nullable=False, comment="upgrade / downgrade / lateral")
    effective_at = Column(DateTime, nullable=True, comment="変更適用予定日時 (NULLなら即時適用済み)")
    applied = Column(Boolean, nullable=False, default=False, comment="適用済みフラグ")
    stripe_event_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
