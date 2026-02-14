"""公開プランAPI"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.plan import Plan
from app.models.plan_question import PlanQuestion

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("")
async def list_public_plans(db: Session = Depends(get_db)):
    """公開プラン一覧 (アクティブのみ)"""
    plans = db.query(Plan).filter(Plan.is_active == True).order_by(Plan.sort_order.asc(), Plan.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
        }
        for p in plans
    ]


@router.get("/{plan_id}")
async def get_plan_detail(plan_id: int, db: Session = Depends(get_db)):
    """プラン詳細 (質問項目含む)"""
    plan = db.query(Plan).filter(Plan.id == plan_id, Plan.is_active == True).first()
    if not plan:
        raise HTTPException(status_code=404, detail="プランが見つかりません")

    questions = db.query(PlanQuestion).filter(
        PlanQuestion.plan_id == plan_id
    ).order_by(PlanQuestion.sort_order).all()

    return {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "price": plan.price,
        "questions": [
            {
                "id": q.id,
                "var_name": q.var_name,
                "label": q.label,
                "question_type": q.question_type,
                "options": q.options,
                "array_max": q.array_max,
                "array_min": q.array_min,
                "is_required": q.is_required,
            }
            for q in questions
        ],
    }
