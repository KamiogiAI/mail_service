"""管理画面: 購読管理 (プラン別グループ表示)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.models.plan import Plan
from app.models.user import User
from app.models.subscription import Subscription
from app.models.plan_question import PlanQuestion
from app.models.user_answer import UserAnswer
from app.models.user_answer_history import UserAnswerHistory
from app.routers.deps import require_admin

router = APIRouter(prefix="/api/admin/subscriptions", tags=["admin-subscriptions"])

ACTIVE_STATUSES = ("trialing", "active", "past_due", "admin_added")


@router.get("")
async def list_subscriptions(db: Session = Depends(get_db), _=Depends(require_admin)):
    """購読一覧 (プラン別グループ)"""
    plans = db.query(Plan).order_by(Plan.created_at.desc()).all()

    result = []
    for plan in plans:
        subs = (
            db.query(Subscription, User)
            .join(User, Subscription.user_id == User.id)
            .filter(
                Subscription.plan_id == plan.id,
                Subscription.status.in_(ACTIVE_STATUSES),
                User.is_active == True,
            )
            .order_by(Subscription.created_at.desc())
            .all()
        )

        if not subs:
            continue

        subscribers = []
        trialing_count = 0
        active_count = 0
        admin_added_count = 0
        cancel_scheduled_count = 0

        for sub, user in subs:
            if sub.status == "admin_added":
                admin_added_count += 1
            elif sub.status == "trialing":
                trialing_count += 1
            elif sub.status in ("active", "past_due"):
                active_count += 1
            if sub.cancel_at_period_end:
                cancel_scheduled_count += 1

            subscribers.append({
                "subscription_id": sub.id,
                "user_id": user.id if user else None,
                "email": user.email if user else "(削除済み)",
                "name": f"{user.name_last} {user.name_first}" if user else "(削除済み)",
                "member_no": sub.member_no_snapshot,
                "status": sub.status,
                "cancel_at_period_end": sub.cancel_at_period_end,
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
                "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
                "created_at": sub.created_at.isoformat() if sub.created_at else None,
            })

        # 月額合計は admin_added を含めない (支払いなし)
        total_revenue = plan.price * (active_count + trialing_count)

        result.append({
            "plan_id": plan.id,
            "plan_name": plan.name,
            "price": plan.price,
            "subscriber_count": len(subscribers),
            "active_count": active_count,
            "trialing_count": trialing_count,
            "admin_added_count": admin_added_count,
            "cancel_scheduled_count": cancel_scheduled_count,
            "total_monthly_revenue": total_revenue,
            "subscribers": subscribers,
        })

    return result


@router.get("/{subscription_id}/detail")
async def get_subscription_detail(
    subscription_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """購読詳細 (購読情報・ユーザー情報・質問回答)"""
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="購読が見つかりません")

    plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()

    # 購読情報
    subscription_data = {
        "id": sub.id,
        "status": sub.status,
        "cancel_at_period_end": sub.cancel_at_period_end,
        "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "stripe_subscription_id": sub.stripe_subscription_id,
    }

    # ユーザー情報
    user_data = None
    answers_data = []

    if sub.user_id:
        user = db.query(User).filter(User.id == sub.user_id).first()
        if user:
            user_data = {
                "id": user.id,
                "member_no": user.member_no,
                "email": user.email,
                "name_last": user.name_last,
                "name_first": user.name_first,
                "trial_used": user.trial_used,
                "deliverable": user.deliverable,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }

            # 質問回答取得 (me.py と同じ carryover ロジック)
            questions = db.query(PlanQuestion).filter(
                PlanQuestion.plan_id == sub.plan_id
            ).order_by(PlanQuestion.sort_order).all()

            answers = db.query(UserAnswer).filter(UserAnswer.user_id == user.id).all()
            answer_map = {a.question_id: a.answer_value for a in answers}

            for q in questions:
                existing_answer = answer_map.get(q.id, "")
                carried_over = False

                if not existing_answer:
                    other_answer = db.query(UserAnswer).join(
                        PlanQuestion, UserAnswer.question_id == PlanQuestion.id
                    ).filter(
                        UserAnswer.user_id == user.id,
                        PlanQuestion.var_name == q.var_name,
                        PlanQuestion.plan_id != sub.plan_id,
                        UserAnswer.answer_value != None,
                        UserAnswer.answer_value != "",
                    ).first()
                    if other_answer:
                        existing_answer = other_answer.answer_value
                        carried_over = True

                answers_data.append({
                    "question_id": q.id,
                    "var_name": q.var_name,
                    "label": q.label,
                    "question_type": q.question_type,
                    "options": q.options,
                    "is_required": q.is_required,
                    "track_changes": q.track_changes,
                    "array_max": q.array_max,
                    "array_min": q.array_min,
                    "answer": existing_answer,
                    "carried_over": carried_over,
                })

    return {
        "subscription": subscription_data,
        "user": user_data,
        "plan": {"id": plan.id, "name": plan.name} if plan else None,
        "answers": answers_data,
    }


class AdminSaveAnswers(BaseModel):
    answers: list[dict]


@router.put("/{subscription_id}/answers")
async def save_subscription_answers(
    subscription_id: int,
    data: AdminSaveAnswers,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """管理者による回答保存 (track_changes 履歴記録付き)"""
    sub = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="購読が見つかりません")
    if not sub.user_id:
        raise HTTPException(status_code=400, detail="退会済みユーザーの回答は編集できません")

    user = db.query(User).filter(User.id == sub.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="ユーザーが見つかりません")

    # track_changes=True の質問IDセットを取得
    tracked_questions = db.query(PlanQuestion).filter(
        PlanQuestion.plan_id == sub.plan_id,
        PlanQuestion.track_changes == True,
    ).all()
    tracked_map = {q.id: q for q in tracked_questions}

    for ans in data.answers:
        qid = ans.get("question_id")
        value = ans.get("answer", "")
        if not qid:
            continue

        existing = db.query(UserAnswer).filter(
            UserAnswer.user_id == user.id,
            UserAnswer.question_id == qid,
        ).first()

        if existing:
            old_value = existing.answer_value or ""
            new_value = str(value)

            if qid in tracked_map and old_value != new_value:
                q_obj = tracked_map[qid]
                history = UserAnswerHistory(
                    user_id=user.id,
                    question_id=qid,
                    var_name=q_obj.var_name,
                    plan_id=sub.plan_id,
                    old_value=old_value,
                    new_value=new_value,
                )
                db.add(history)

            existing.answer_value = new_value
        else:
            ua = UserAnswer(user_id=user.id, question_id=qid, answer_value=str(value))
            db.add(ua)

    db.commit()
    return {"message": "回答を保存しました"}
