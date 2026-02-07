"""マイページAPI"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.rate_limit import limiter, VERIFY_CODE_RATE_LIMIT
from app.core.session import invalidate_user_sessions
from app.models.user import User
from app.models.subscription import Subscription
from app.models.plan import Plan
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
from app.models.user_answer import UserAnswer
from app.models.user_answer_history import UserAnswerHistory
from app.models.plan_question import PlanQuestion
from app.services import auth_service, stripe_service
from app.services.mail_service import send_password_change_code_email
from app.schemas.auth import (
    PasswordChangeRequestSchema,
    PasswordChangeConfirmSchema,
    PasswordChangeResponse,
)
from app.routers.deps import require_login

router = APIRouter(prefix="/api/me", tags=["me"])


class ProfileUpdate(BaseModel):
    name_last: Optional[str] = None
    name_first: Optional[str] = None
    email: Optional[EmailStr] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.get("/profile")
async def get_profile(user: User = Depends(require_login)):
    """プロフィール取得"""
    return {
        "member_no": user.member_no,
        "email": user.email,
        "name_last": user.name_last,
        "name_first": user.name_first,
        "deliverable": user.deliverable,
    }


@router.put("/profile")
async def update_profile(
    data: ProfileUpdate,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """プロフィール更新"""
    if data.name_last is not None:
        user.name_last = data.name_last
    if data.name_first is not None:
        user.name_first = data.name_first
    if data.email is not None and data.email != user.email:
        existing = auth_service.get_user_by_email(db, data.email)
        if existing:
            raise HTTPException(status_code=400, detail="このメールアドレスは既に使用されています")
        user.email = data.email
    db.commit()
    return {"message": "プロフィールを更新しました"}


@router.post("/password-change/request", response_model=PasswordChangeResponse)
@limiter.limit(VERIFY_CODE_RATE_LIMIT)
async def request_password_change(
    request: Request,
    data: PasswordChangeRequestSchema,
    user: User = Depends(require_login),
    r=Depends(get_redis),
):
    """パスワード変更リクエスト（2FA: 認証コード送信）"""
    # 現在のパスワードを検証
    if not auth_service.verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="現在のパスワードが正しくありません")

    # 認証コード生成
    code = await auth_service.generate_verify_code(r, user.id)
    if code is None:
        raise HTTPException(status_code=429, detail="認証がロックされています。しばらくお待ちください。")

    # 認証コードをメール送信
    success = send_password_change_code_email(
        to_email=user.email,
        name=f"{user.name_last} {user.name_first}",
        code=code,
    )
    if not success:
        raise HTTPException(status_code=500, detail="認証コードの送信に失敗しました。しばらくしてからお試しください。")

    # 一時トークン生成
    token = await auth_service.create_password_change_token(r, user.id)

    return PasswordChangeResponse(
        message="認証コードをメールに送信しました",
        token=token,
    )


@router.post("/password-change/confirm", response_model=PasswordChangeResponse)
@limiter.limit(VERIFY_CODE_RATE_LIMIT)
async def confirm_password_change(
    request: Request,
    data: PasswordChangeConfirmSchema,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
    r=Depends(get_redis),
):
    """パスワード変更確認（2FA: 認証コード検証 + パスワード更新）"""
    # 一時トークン検証（消費しない - コード検証が先）
    token_user_id = await auth_service.validate_password_change_token(r, data.token)
    if token_user_id is None:
        raise HTTPException(status_code=400, detail="トークンが無効または期限切れです")

    # トークンのユーザーIDとログインユーザーが一致するか確認
    if token_user_id != user.id:
        raise HTTPException(status_code=400, detail="トークンが無効です")

    # 認証コード検証
    success, msg = await auth_service.verify_code(r, user.id, data.code)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    # トークン消費（コード検証成功後）
    await auth_service.consume_password_change_token(r, data.token)

    # パスワード更新
    user.password_hash = auth_service.hash_password(data.new_password)
    db.commit()

    # 他のセッションを無効化（現在のセッションは維持）
    current_session_id = request.cookies.get("session_id")
    destroyed_count = await invalidate_user_sessions(r, user.id, exclude_session_id=current_session_id)

    return PasswordChangeResponse(message="パスワードを変更しました")


@router.get("/delivery-history")
async def delivery_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """配信履歴 (件名のみ)"""
    q = db.query(DeliveryItem, Delivery).join(
        Delivery, DeliveryItem.delivery_id == Delivery.id
    ).filter(
        DeliveryItem.user_id == user.id,
        DeliveryItem.status == 2,  # 完了のみ
    ).order_by(DeliveryItem.sent_at.desc())

    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "items": [
            {
                "subject": delivery.subject or "(件名なし)",
                "sent_at": item.sent_at.isoformat() if item.sent_at else None,
            }
            for item, delivery in items
        ],
    }


@router.get("/answers/{plan_id}")
async def get_answers(
    plan_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """質問回答取得 (他プランからの var_name 一致引き継ぎ付き)"""
    questions = db.query(PlanQuestion).filter(PlanQuestion.plan_id == plan_id).order_by(PlanQuestion.sort_order).all()
    answers = db.query(UserAnswer).filter(UserAnswer.user_id == user.id).all()
    answer_map = {a.question_id: a.answer_value for a in answers}

    result = []
    for q in questions:
        existing_answer = answer_map.get(q.id, "")
        carried_over = False

        # 未回答なら他プランの同一 var_name から引き継ぎ
        if not existing_answer:
            other_answer = db.query(UserAnswer).join(
                PlanQuestion, UserAnswer.question_id == PlanQuestion.id
            ).filter(
                UserAnswer.user_id == user.id,
                PlanQuestion.var_name == q.var_name,
                PlanQuestion.plan_id != plan_id,
                UserAnswer.answer_value != None,
                UserAnswer.answer_value != "",
            ).first()
            if other_answer:
                existing_answer = other_answer.answer_value
                carried_over = True

        result.append({
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

    return result


@router.post("/answers/{plan_id}")
async def save_answers(
    plan_id: int,
    answers: list[dict],
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """質問回答保存 (track_changes=True の質問は変更履歴を記録)"""
    # プランアクセス権チェック: 購読中またはこれから購読するプランのみ許可
    active_statuses = ["trialing", "active", "admin_added"]
    has_subscription = db.query(Subscription).filter(
        Subscription.user_id == user.id,
        Subscription.plan_id == plan_id,
        Subscription.status.in_(active_statuses),
    ).first()

    # 購読がない場合、プラン自体が存在するかチェック（新規購読フロー対応）
    if not has_subscription:
        plan = db.query(Plan).filter(Plan.id == plan_id, Plan.is_active == True).first()
        if not plan:
            raise HTTPException(status_code=404, detail="プランが見つかりません")

    # track_changes=True の質問IDセットを取得
    tracked_questions = db.query(PlanQuestion).filter(
        PlanQuestion.plan_id == plan_id,
        PlanQuestion.track_changes == True,
    ).all()
    tracked_map = {q.id: q for q in tracked_questions}

    for ans in answers:
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

            # 変更履歴記録 (track_changes=True かつ値が変わった場合)
            if qid in tracked_map and old_value != new_value:
                q_obj = tracked_map[qid]
                history = UserAnswerHistory(
                    user_id=user.id,
                    question_id=qid,
                    var_name=q_obj.var_name,
                    plan_id=plan_id,
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


@router.get("/answer-history")
async def get_answer_history(
    plan_id: int = Query(...),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """回答変更履歴一覧 (古い順、上限200)"""
    # 質問のlabel辞書を先に構築
    questions = db.query(PlanQuestion).filter(PlanQuestion.plan_id == plan_id).all()
    label_map = {q.id: q.label for q in questions}
    # var_nameからもlabelを引けるように
    var_label_map = {q.var_name: q.label for q in questions}

    histories = (
        db.query(UserAnswerHistory)
        .filter(
            UserAnswerHistory.user_id == user.id,
            UserAnswerHistory.plan_id == plan_id,
        )
        .order_by(UserAnswerHistory.changed_at.asc())
        .limit(200)
        .all()
    )

    return [
        {
            "id": h.id,
            "var_name": h.var_name,
            "label": label_map.get(h.question_id) or var_label_map.get(h.var_name) or h.var_name,
            "old_value": h.old_value,
            "new_value": h.new_value,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
        }
        for h in histories
    ]


@router.delete("/account")
async def delete_account(
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """退会 (Stripe購読解約 → user_id NULL化 → 物理削除)"""
    # 全購読解約
    subs = db.query(Subscription).filter(
        Subscription.user_id == user.id,
        Subscription.status.in_(["trialing", "active", "admin_added"]),
    ).all()
    for sub in subs:
        if sub.stripe_subscription_id:
            try:
                stripe_service.cancel_subscription_immediately(sub.stripe_subscription_id)
            except Exception:
                pass
        sub.status = "canceled"
        sub.user_id = None

    # 関連テーブルuser_id NULL化
    from app.models.delivery_item import DeliveryItem
    from app.models.system_log import SystemLog
    from app.models.progress_task import ProgressTask
    db.query(DeliveryItem).filter(DeliveryItem.user_id == user.id).update({"user_id": None})
    db.query(SystemLog).filter(SystemLog.user_id == user.id).update({"user_id": None})
    db.query(ProgressTask).filter(ProgressTask.user_id == user.id).update({"user_id": None})

    db.delete(user)
    db.commit()
    return {"message": "退会処理が完了しました"}


@router.post("/unsubscribe")
async def unsubscribe_delivery(
    token: str,
    db: Session = Depends(get_db),
):
    """配信停止 (ワンクリック)"""
    user = db.query(User).filter(User.unsubscribe_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="無効なトークンです")

    user.deliverable = False
    db.commit()
    return {"message": "配信を停止しました"}
