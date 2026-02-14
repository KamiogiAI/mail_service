"""管理画面: プランCRUD + 質問項目 + あらすじ + 外部データ設定"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.security import encrypt, decrypt
from app.models.plan import Plan
from app.models.plan_question import PlanQuestion
from app.models.plan_summary_setting import PlanSummarySetting
from app.models.plan_external_data_setting import PlanExternalDataSetting
from app.services import stripe_service, subscription_service
from app.routers.deps import require_admin
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin/plans", tags=["admin-plans"])


# --- スキーマ ---
class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: int = Field(ge=0)
    schedule_type: str = "daily"
    schedule_weekdays: Optional[list[int]] = None
    send_time: str  # "HH:MM"
    sheets_id: Optional[str] = None
    model: str = "gpt-4o-mini"
    system_prompt: Optional[str] = None
    prompt: str
    batch_send_enabled: bool = False
    trial_enabled: bool = True


class PlanUpdate(PlanCreate):
    is_active: Optional[bool] = None


class QuestionItem(BaseModel):
    id: Optional[int] = None
    var_name: str
    label: str
    question_type: str = "text"
    options: Optional[list[str]] = None
    array_max: Optional[int] = None
    array_min: Optional[int] = None
    is_required: bool = True
    track_changes: bool = False
    sort_order: int = 0


class SummarySettingData(BaseModel):
    summary_prompt: str
    summary_length_target: int = 200
    summary_max_keep: int = 10
    summary_inject_count: int = 3


class ExternalDataSettingData(BaseModel):
    external_data_path: str
    firebase_credential_id: Optional[int] = None  # 認証情報ID
    delete_after_process: bool = False  # 処理後に削除
    firebase_key_json: Optional[str] = None  # [後方互換] 平文JSON (保存時に暗号化)


class TestExternalDataRequest(BaseModel):
    external_data_path: str
    firebase_credential_id: Optional[int] = None  # 認証情報ID
    firebase_key_json: Optional[str] = None  # 平文JSON (未保存時)
    plan_id: Optional[int] = None            # 保存済み設定使用時


class TestSheetsRequest(BaseModel):
    sheets_id: str


# --- ルート ---
@router.get("")
async def list_plans(db: Session = Depends(get_db), _=Depends(require_admin)):
    """プラン一覧"""
    plans = db.query(Plan).order_by(Plan.created_at.desc()).all()
    result = []
    for p in plans:
        from app.models.subscription import Subscription
        from app.models.user import User
        sub_count = db.query(Subscription).join(User, Subscription.user_id == User.id).filter(
            Subscription.plan_id == p.id,
            Subscription.status.in_(["trialing", "active", "admin_added"]),
            User.is_active == True,
        ).count()
        result.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "is_active": p.is_active,
            "schedule_type": p.schedule_type,
            "send_time": p.send_time.strftime("%H:%M") if p.send_time else None,
            "model": p.model,
            "batch_send_enabled": p.batch_send_enabled,
            "trial_enabled": p.trial_enabled,
            "subscriber_count": sub_count,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return result


@router.get("/{plan_id}")
async def get_plan(plan_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """プラン詳細"""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="プランが見つかりません")

    questions = db.query(PlanQuestion).filter(
        PlanQuestion.plan_id == plan_id
    ).order_by(PlanQuestion.sort_order).all()

    summary = db.query(PlanSummarySetting).filter(
        PlanSummarySetting.plan_id == plan_id
    ).first()

    external = db.query(PlanExternalDataSetting).filter(
        PlanExternalDataSetting.plan_id == plan_id
    ).first()

    return {
        "id": plan.id,
        "name": plan.name,
        "description": plan.description,
        "price": plan.price,
        "is_active": plan.is_active,
        "stripe_product_id": plan.stripe_product_id,
        "stripe_price_id": plan.stripe_price_id,
        "schedule_type": plan.schedule_type,
        "schedule_weekdays": plan.schedule_weekdays,
        "send_time": plan.send_time.strftime("%H:%M") if plan.send_time else None,
        "sheets_id": plan.sheets_id,
        "model": plan.model,
        "system_prompt": plan.system_prompt,
        "prompt": plan.prompt,
        "batch_send_enabled": plan.batch_send_enabled,
        "trial_enabled": plan.trial_enabled,
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
                "track_changes": q.track_changes,
                "sort_order": q.sort_order,
            }
            for q in questions
        ],
        "summary_setting": {
            "summary_prompt": summary.summary_prompt,
            "summary_length_target": summary.summary_length_target,
            "summary_max_keep": summary.summary_max_keep,
            "summary_inject_count": summary.summary_inject_count,
        } if summary else None,
        "external_data_setting": {
            "external_data_path": external.external_data_path,
            "firebase_credential_id": external.firebase_credential_id,
            "delete_after_process": external.delete_after_process,
            "has_firebase_key": bool(external.firebase_key_json_enc),  # 後方互換
        } if external else None,
    }


@router.post("")
async def create_plan(data: PlanCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    """プラン作成"""
    from datetime import time
    try:
        h, m = data.send_time.split(":")
        int(h); int(m)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="send_timeの形式が不正です（HH:MM）")

    plan = Plan(
        name=data.name,
        description=data.description,
        price=data.price,
        schedule_type=data.schedule_type,
        schedule_weekdays=data.schedule_weekdays,
        send_time=time(int(h), int(m)),
        sheets_id=data.sheets_id,
        model=data.model,
        system_prompt=data.system_prompt,
        prompt=data.prompt,
        batch_send_enabled=data.batch_send_enabled,
        trial_enabled=data.trial_enabled,
    )

    # Stripe Product/Price作成
    if data.price > 0:
        try:
            product_id, price_id = stripe_service.create_product_and_price(
                name=data.name,
                description=data.description or "",
                price_yen=data.price,
            )
            plan.stripe_product_id = product_id
            plan.stripe_price_id = price_id
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Stripe連携エラー: {e}")

    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, "message": "プランを作成しました"}


@router.put("/{plan_id}")
async def update_plan(plan_id: int, data: PlanUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    """プラン更新"""
    from datetime import time
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="プランが見つかりません")

    try:
        h, m = data.send_time.split(":")
        int(h); int(m)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="send_timeの形式が不正です（HH:MM）")
    plan.name = data.name
    plan.description = data.description
    plan.price = data.price
    plan.schedule_type = data.schedule_type
    plan.schedule_weekdays = data.schedule_weekdays
    plan.send_time = time(int(h), int(m))
    plan.sheets_id = data.sheets_id
    plan.model = data.model
    plan.system_prompt = data.system_prompt
    plan.prompt = data.prompt
    plan.batch_send_enabled = data.batch_send_enabled
    plan.trial_enabled = data.trial_enabled
    if data.is_active is not None:
        plan.is_active = data.is_active

    # Stripe Product更新
    if plan.stripe_product_id:
        try:
            stripe_service.update_product(plan.stripe_product_id, data.name, data.description or "")
        except Exception as e:
            logger.warning(f"Stripe Product更新失敗 (product_id={plan.stripe_product_id}): {e}")

    db.commit()
    return {"message": "プランを更新しました"}


@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: int,
    at_period_end: bool = False,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """プラン削除
    
    at_period_end=False: 即時削除（全購読強制解約）
    at_period_end=True: 期間終了後に削除（解約予約）
    """
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="プランが見つかりません")

    if at_period_end:
        # 期間終了後に削除: プランを非表示化＆削除予約
        plan.is_active = False
        plan.pending_delete = True
        
        # 全購読を解約予約（期間終了時にキャンセル）
        subscription_service.schedule_cancel_plan_subscriptions(db, plan_id)
        
        # Stripe Product アーカイブ（新規加入不可に）
        if plan.stripe_product_id:
            try:
                stripe_service.archive_product(plan.stripe_product_id)
            except Exception:
                pass
        
        db.commit()
        return {"message": "プランの削除を予約しました。全ユーザーの期間終了後に削除されます。"}
    else:
        # 即時削除: 全購読強制解約
        subscription_service.force_cancel_plan_subscriptions(db, plan_id)

        # Stripe Product アーカイブ
        if plan.stripe_product_id:
            try:
                stripe_service.archive_product(plan.stripe_product_id)
            except Exception:
                pass

        db.delete(plan)
        db.commit()
        return {"message": "プランを削除しました"}


# --- 質問項目 ---
@router.put("/{plan_id}/questions")
async def update_questions(
    plan_id: int,
    questions: list[QuestionItem],
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """質問項目一括更新 (var_nameで既存回答を保持)"""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="プランが見つかりません")

    # 既存の質問をvar_name→PlanQuestionでマップ
    existing_questions = db.query(PlanQuestion).filter(
        PlanQuestion.plan_id == plan_id
    ).all()
    existing_map = {pq.var_name: pq for pq in existing_questions}

    # 新しいvar_nameのセット
    new_var_names = {q.var_name for q in questions}

    # 更新または新規作成
    for i, q in enumerate(questions):
        if q.var_name in existing_map:
            # 既存質問を更新 (question_idは維持 → 回答も保持される)
            pq = existing_map[q.var_name]
            pq.label = q.label
            pq.question_type = q.question_type
            pq.options = q.options
            pq.array_max = q.array_max
            pq.array_min = q.array_min
            pq.is_required = q.is_required
            pq.track_changes = q.track_changes
            pq.sort_order = q.sort_order if q.sort_order else i
        else:
            # 新規作成
            pq = PlanQuestion(
                plan_id=plan_id,
                var_name=q.var_name,
                label=q.label,
                question_type=q.question_type,
                options=q.options,
                array_max=q.array_max,
                array_min=q.array_min,
                is_required=q.is_required,
                track_changes=q.track_changes,
                sort_order=q.sort_order if q.sort_order else i,
            )
            db.add(pq)

    # 削除された質問を削除 (CASCADE DELETEで回答も消える)
    for var_name, pq in existing_map.items():
        if var_name not in new_var_names:
            db.delete(pq)

    db.commit()
    return {"message": "質問項目を更新しました"}


# --- あらすじ設定 ---
@router.put("/{plan_id}/summary-setting")
async def update_summary_setting(
    plan_id: int,
    data: SummarySettingData,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """あらすじ設定更新"""
    setting = db.query(PlanSummarySetting).filter(
        PlanSummarySetting.plan_id == plan_id
    ).first()

    if setting:
        setting.summary_prompt = data.summary_prompt
        setting.summary_length_target = data.summary_length_target
        setting.summary_max_keep = data.summary_max_keep
        setting.summary_inject_count = data.summary_inject_count
    else:
        setting = PlanSummarySetting(
            plan_id=plan_id,
            summary_prompt=data.summary_prompt,
            summary_length_target=data.summary_length_target,
            summary_max_keep=data.summary_max_keep,
            summary_inject_count=data.summary_inject_count,
        )
        db.add(setting)

    db.commit()
    return {"message": "あらすじ設定を更新しました"}


@router.delete("/{plan_id}/summary-setting")
async def delete_summary_setting(
    plan_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """あらすじ設定削除"""
    db.query(PlanSummarySetting).filter(PlanSummarySetting.plan_id == plan_id).delete()
    db.commit()
    return {"message": "あらすじ設定を削除しました"}


# --- 動作チェック ---
@router.post("/test-external-data")
async def test_external_data(
    data: TestExternalDataRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Firebase外部データ動作チェック"""
    from app.services.firestore_external_service import load_external_data
    from app.models.firebase_credential import FirebaseCredential

    firebase_key_enc = None

    # 1. 直接JSONが渡された場合 (後方互換)
    if data.firebase_key_json:
        firebase_key_enc = encrypt(data.firebase_key_json)
    # 2. 認証情報IDが指定された場合
    elif data.firebase_credential_id:
        credential = db.query(FirebaseCredential).filter(
            FirebaseCredential.id == data.firebase_credential_id
        ).first()
        if credential:
            firebase_key_enc = credential.encrypted_json
    # 3. プランIDから設定を取得
    elif data.plan_id:
        setting = db.query(PlanExternalDataSetting).filter(
            PlanExternalDataSetting.plan_id == data.plan_id
        ).first()
        if setting:
            if setting.firebase_credential_id:
                credential = db.query(FirebaseCredential).filter(
                    FirebaseCredential.id == setting.firebase_credential_id
                ).first()
                if credential:
                    firebase_key_enc = credential.encrypted_json
            elif setting.firebase_key_json_enc:
                firebase_key_enc = setting.firebase_key_json_enc

    if not firebase_key_enc:
        return {"ok": False, "error": "Firebase認証情報が設定されていません"}

    try:
        data_str, split_items = load_external_data(data.external_data_path, firebase_key_enc)
        is_split = data.external_data_path.rstrip("/").endswith("~")

        if is_split and split_items:
            return {
                "ok": True,
                "split": True,
                "keys": [name for name, _ in split_items],
            }
        else:
            preview = data_str[:500] if data_str else ""
            return {
                "ok": True,
                "split": False,
                "preview": preview,
            }
    except Exception as e:
        logger.error(f"外部データテストエラー: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/test-sheets")
async def test_sheets(
    data: TestSheetsRequest,
    _=Depends(require_admin),
):
    """Google Sheets動作チェック"""
    from app.services.sheets_service import test_sheets_connection
    return test_sheets_connection(data.sheets_id)


# --- 外部データ設定 ---
@router.put("/{plan_id}/external-data-setting")
async def update_external_data_setting(
    plan_id: int,
    data: ExternalDataSettingData,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """外部データ設定更新"""
    setting = db.query(PlanExternalDataSetting).filter(
        PlanExternalDataSetting.plan_id == plan_id
    ).first()

    # 後方互換: 直接JSONが渡された場合
    firebase_enc = None
    if data.firebase_key_json:
        firebase_enc = encrypt(data.firebase_key_json)

    if setting:
        setting.external_data_path = data.external_data_path
        setting.delete_after_process = data.delete_after_process
        if data.firebase_credential_id is not None:
            setting.firebase_credential_id = data.firebase_credential_id
        if firebase_enc:
            setting.firebase_key_json_enc = firebase_enc
    else:
        setting = PlanExternalDataSetting(
            plan_id=plan_id,
            external_data_path=data.external_data_path,
            firebase_credential_id=data.firebase_credential_id,
            delete_after_process=data.delete_after_process,
            firebase_key_json_enc=firebase_enc,
        )
        db.add(setting)

    db.commit()
    return {"message": "外部データ設定を更新しました"}


@router.delete("/{plan_id}/external-data-setting")
async def delete_external_data_setting(
    plan_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """外部データ設定削除"""
    db.query(PlanExternalDataSetting).filter(PlanExternalDataSetting.plan_id == plan_id).delete()
    db.commit()
    return {"message": "外部データ設定を削除しました"}
