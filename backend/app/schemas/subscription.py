from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SubscribeRequest(BaseModel):
    plan_id: int
    promotion_code: Optional[str] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CheckoutCompleteRequest(BaseModel):
    session_id: str


class BillingPortalRequest(BaseModel):
    return_url: Optional[str] = None


class SubscriptionInfo(BaseModel):
    id: int
    plan_id: int
    plan_name: Optional[str] = None
    plan_price: Optional[int] = None
    status: str
    cancel_at_period_end: bool
    current_period_end: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    scheduled_plan_name: Optional[str] = None
    scheduled_change_at: Optional[datetime] = None
    # 割引情報
    discount_name: Optional[str] = None  # クーポン/プロモーション名
    discount_percent: Optional[float] = None  # 割引率（%）
    discount_amount: Optional[int] = None  # 割引額（円）
    actual_price: Optional[int] = None  # 実際の請求額（割引後）

    model_config = {"from_attributes": True}
