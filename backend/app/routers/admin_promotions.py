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


class PromotionCodeUpdate(BaseModel):
    code: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[int] = None
    max_redemptions: Optional[int] = None
    expires_at: Optional[str] = None
    eligible_plan_ids: Optional[list[int]] = None

    @field_validator("discount_type")
    @classmethod
    def validate_discount_type(cls, v):
        if v is not None and v not in ("percent_off", "amount_off"):
            raise ValueError("discount_typeは 'percent_off' または 'amount_off' のみ有効です")
        return v

    @field_validator("discount_value")
    @classmethod
    def validate_discount_value(cls, v):
        if v is not None and v <= 0:
            raise ValueError("discount_valueは1以上の値を指定してください")
        return v


@router.put("/{promo_id}")
async def update_promotion(
    promo_id: int,
    data: PromotionCodeUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """プロモーションコード編集
    
    コード変更時は内部的にStripeの古いプロモーションコードを無効化し、新規作成する。
    割引条件（discount_type, discount_value, eligible_plan_ids）が変更された場合も
    新しいクーポン＆プロモーションコードを作成する。
    """
    promo = db.query(PromotionCode).filter(PromotionCode.id == promo_id).first()
    if not promo:
        raise HTTPException(status_code=404, detail="プロモーションコードが見つかりません")

    # コード重複チェック
    new_code = data.code if data.code else promo.code
    if data.code and data.code != promo.code:
        existing = db.query(PromotionCode).filter(
            PromotionCode.code == data.code,
            PromotionCode.id != promo_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="このコードは既に存在します")

    # Stripe再作成が必要かどうか判定
    needs_stripe_recreate = (
        (data.code and data.code != promo.code) or
        (data.discount_type and data.discount_type != promo.discount_type) or
        (data.discount_value and data.discount_value != promo.discount_value) or
        (data.eligible_plan_ids is not None and data.eligible_plan_ids != promo.eligible_plan_ids) or
        (data.max_redemptions is not None and data.max_redemptions != promo.max_redemptions) or
        (data.expires_at is not None)
    )

    if needs_stripe_recreate:
        # 古いStripeプロモーションコードを無効化
        if promo.stripe_promotion_code_id:
            try:
                stripe_service.deactivate_promotion_code(promo.stripe_promotion_code_id)
            except Exception:
                pass  # 既に無効化されている場合など

        # 新しい値を決定
        discount_type = data.discount_type if data.discount_type else promo.discount_type
        discount_value = data.discount_value if data.discount_value else promo.discount_value
        eligible_plan_ids = data.eligible_plan_ids if data.eligible_plan_ids is not None else promo.eligible_plan_ids
        max_redemptions = data.max_redemptions if data.max_redemptions is not None else promo.max_redemptions

        # eligible_plan_idsからStripeプロダクトIDを取得
        applies_to_products = None
        if eligible_plan_ids:
            plans = db.query(Plan).filter(Plan.id.in_(eligible_plan_ids)).all()
            applies_to_products = [p.stripe_product_id for p in plans if p.stripe_product_id]

        # 新しいStripe Coupon作成
        try:
            coupon_id = stripe_service.create_coupon(
                discount_type=discount_type,
                discount_value=discount_value,
                name=f"Promo: {new_code}",
                applies_to_products=applies_to_products,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Stripe Coupon作成エラー: {e}")

        # 新しいStripe Promotion Code作成
        expires_timestamp = None
        if data.expires_at:
            try:
                expires_timestamp = int(parse_expires_date(data.expires_at).timestamp())
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="expires_atの日付形式が不正です")
        elif promo.expires_at:
            expires_timestamp = int(promo.expires_at.timestamp())

        try:
            new_promo_id = stripe_service.create_promotion_code(
                coupon_id=coupon_id,
                code=new_code,
                max_redemptions=max_redemptions,
                expires_at=expires_timestamp,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Stripe Promotion Code作成エラー: {e}")

        # DB更新
        promo.stripe_promotion_code_id = new_promo_id
        promo.stripe_coupon_id = coupon_id
        promo.code = new_code
        promo.discount_type = discount_type
        promo.discount_value = discount_value
        promo.eligible_plan_ids = eligible_plan_ids
        promo.max_redemptions = max_redemptions
        if data.expires_at:
            promo.expires_at = parse_expires_date(data.expires_at)
        promo.is_active = True  # 再有効化

    else:
        # Stripe再作成不要な場合（現状はない）
        pass

    db.commit()
    return {"message": "プロモーションコードを更新しました"}


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
