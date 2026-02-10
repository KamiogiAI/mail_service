from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SAEnum, ForeignKey, func
from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    member_no_snapshot = Column(String(8), nullable=False, comment="会員番号スナップショット")
    stripe_subscription_id = Column(String(255), nullable=True, unique=True)
    status = Column(
        SAEnum("trialing", "active", "past_due", "canceled", "unpaid", "incomplete", "admin_added",
               name="subscription_status"),
        nullable=False,
        default="active",
    )
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    scheduled_plan_id = Column(Integer, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, comment="ダウングレード予定プランID")
    scheduled_change_at = Column(DateTime, nullable=True, comment="プラン変更予定日時")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
