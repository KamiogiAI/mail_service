"""管理画面: プロモーションコード管理"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, field_validator
from datetime import datetime, time
import time as time_mod


def parse_expires_date(date_str: str) -> datetime:
    """日付文字列をパース。日付のみの場合は23:59:59を設定"""
    dt = datetime.fromisoformat(date_str)
    # 日付のみ（時刻なし）の場合、その日の終わりに設定
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and "T" not in date_str:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt

from app.core.database import get_db
from app.models.promotion_code import PromotionCode
from app.models.plan import Plan
from app.services import stripe_service
from app.routers.deps import require_admin

router = APIRouter(prefix="/api/admin/promotions", tags=["admin-promotions"])


class PromotionCodeCreate(BaseModel):
    code: str
    discount_type: str  # "percent_off" or "amount_off"
    discount_value: int
    max_redemptions: Optional[int] = None
    expires_at: Optional[str] = None  # ISO datetime
    eligible_plan_ids: Optional[list[int]] = None

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, v):
        if v not in ("percent_off", "amount_off"):
            raise ValueError("discount_typeは 'percent_off' または 'amount_off' のみ有効です")
        return v

    @field_validator("discount_value")
    @classmethod
    def validate_discount_value(cls, v):
        if v <= 0:
            raise ValueError("discount_valueは1以上の値を指定してください")
        return v

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, v):
        if v is None:
            return v
        try:
            expires = parse_expires_date(v)
            now = datetime.now()
            if expires <= now:
                raise ValueError("expires_atは未来の日付を指定してください")
        except ValueError as e:
            if "expires_at" in str(e):
                raise
            raise ValueError("expires_atの日付形式が不正です (YYYY-MM-DD形式で指定)")
        return v


@router.get("")
async def list_promotions(db: Session = Depends(get_db), _=Depends(require_admin)):
    """プロモーションコード一覧"""
    promos = db.query(PromotionCode).order_by(PromotionCode.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "code": p.code,
            "discount_type": p.discount_type,
            "discount_value": p.discount_value,
            "is_active": p.is_active,
            "max_redemptions": p.max_redemptions,
            "times_redeemed": p.times_redeemed,
            "eligible_plan_ids": p.eligible_plan_ids,
            "expires_at": p.expires_at.isoformat() if p.expires_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in promos
    ]


@router.post("")
async def create_promotion(
    data: PromotionCodeCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """プロモーションコード作成"""
    existing = db.query(PromotionCode).filter(PromotionCode.code == data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="このコードは既に存在します")

    # eligible_plan_idsからStripeプロダクトIDを取得
    applies_to_products = None
    if data.eligible_plan_ids:
        plans = db.query(Plan).filter(Plan.id.in_(data.eligible_plan_ids)).all()
        applies_to_products = [p.stripe_product_id for p in plans if p.stripe_product_id]
        if not applies_to_products:
            raise HTTPException(
                status_code=400,
                detail="指定されたプランにStripeプロダクトが設定されていません"
            )

    # Stripe Coupon作成
    try:
        coupon_id = stripe_service.create_coupon(
            discount_type=data.discount_type,
            discount_value=data.discount_value,
            name=f"Promo: {data.code}",
            applies_to_products=applies_to_products,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe Coupon作成エラー: {e}")

    # Stripe Promotion Code作成
    expires_timestamp = None
    if data.expires_at:
        try:
            expires_timestamp = int(parse_expires_date(data.expires_at).timestamp())
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="expires_atの日付形式が不正です")

    try:
        promo_id = stripe_service.create_promotion_code(
            coupon_id=coupon_id,
            code=data.code,
            max_redemptions=data.max_redemptions,
            expires_at=expires_timestamp,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stripe Promotion Code作成エラー: {e}")

    promo = PromotionCode(
        code=data.code,
        stripe_promotion_code_id=promo_id,
        stripe_coupon_id=coupon_id,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        max_redemptions=data.max_redemptions,
        eligible_plan_ids=data.eligible_plan_ids,
        expires_at=parse_expires_date(data.expires_at) if data.expires_at else None,
    )
    db.add(promo)
    db.commit()
    return {"message": "プロモーションコードを作成しました"}


@router.put("/{promo_id}/deactivate")
async def deactivate_promotion(
    promo_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """プロモーションコード無効化"""
    promo = db.query(PromotionCode).filter(PromotionCode.id == promo_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="プロモーションコードが見つかりません")

    if promo.stripe_promotion_code_id:
        try:
            stripe_service.deactivate_promotion_code(promo.stripe_promotion_code_id)
        except Exception:
            pass

    promo.is_active = False
    db.commit()
    return {"message": "プロモーションコードを無効化しました"}
