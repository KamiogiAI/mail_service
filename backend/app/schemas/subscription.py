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

    model_config = {"from_attributes": True}


class ChangePlanRequest(BaseModel):
    new_plan_id: int
