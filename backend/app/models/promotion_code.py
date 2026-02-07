from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, func
from app.core.database import Base


class PromotionCode(Base):
    __tablename__ = "promotion_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), unique=True, nullable=False, comment="プロモーションコード")
    stripe_promotion_code_id = Column(String(255), nullable=True, unique=True)
    stripe_coupon_id = Column(String(255), nullable=True)
    discount_type = Column(String(20), nullable=False, comment="percent_off / amount_off")
    discount_value = Column(Integer, nullable=False, comment="割引値 (% or 円)")
    is_active = Column(Boolean, nullable=False, default=True)
    max_redemptions = Column(Integer, nullable=True, comment="最大使用回数")
    times_redeemed = Column(Integer, nullable=False, default=0)
    eligible_plan_ids = Column(JSON, nullable=True, comment="適用可能プランID一覧 (null=全プラン)")
    expires_at = Column(DateTime, nullable=True, comment="有効期限")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
