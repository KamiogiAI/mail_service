"""送信オーケストレーションサービス"""
import time
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from app.models.plan import Plan
from app.models.plan_question import PlanQuestion
from app.models.plan_external_data_setting import PlanExternalDataSetting
from app.models.firebase_credential import FirebaseCredential
from app.models.subscription import Subscription
from app.models.user import User
from app.models.user_answer import UserAnswer
from app.models.delivery import Delivery
from app.models.delivery_item import DeliveryItem
from app.models.system_log import SystemLog
from app.models.progress_plan import ProgressPlan
from app.services.openai_service import generate_email_content
from app.services.variable_resolver import resolve_variables, build_answers_dict
from app.services.resend_service import send_email
import json
from app.services.firestore_external_service import load_external_data
from app.services.summary_service import (
    get_summary_setting, get_recent_summaries,
    inject_summaries_into_prompt, generate_and_save_summary,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.worker.throttle_manager import check_emergency_stop

logger = get_logger(__name__)
JST = ZoneInfo("Asia/Tokyo")
MAX_RETRY = 3  # 最大リトライ回数

# Heartbeat更新間隔（送信件数）
HEARTBEAT_INTERVAL = 5


def _update_progress_heartbeat(db: Session, progress_id: int, cursor: str = None):
    """
    ProgressPlanのheartbeatを更新する。
    長時間処理中にWatchdogから死亡判定されないために定期的に呼び出す。
    """
    if not progress_id:
        return
    try:
        progress = db.query(ProgressPlan).filter(ProgressPlan.id == progress_id).first()
        if progress and progress.status == 1:
            now = datetime.now(JST)
            progress.heartbeat_at = now
            if cursor:
                progress.cursor = cursor
            db.commit()
    except Exception as e:
        logger.warning(f"Heartbeat更新失敗: {e}")


def _has_user_variables(prompt: str, questions: list) -> bool:
    """プロンプトにユーザー固有の変数が含まれているか判定
    
    質問変数だけでなく、組み込みのユーザー変数も考慮する。
    これらが含まれる場合、ユーザーごとにGPT生成が必要。
    """
    # 組み込みユーザー変数をチェック
    builtin_user_vars = ["{user_name}", "{name_first}", "{name_last}"]
    for var in builtin_user_vars:
        if var in prompt:
            return True
    
    # 質問変数をチェック
    if not questions:
        return False
    for q in questions:
        if "{" + q.var_name + "}" in prompt:
            return True
    return False


def execute_plan_delivery(
    db: Session,
    plan: Plan,
    send_type: str = "scheduled",
    prompt_override: str = None,
    throttle_seconds: int = 5,
    target_user_id: int = None,
    api_key: str = None,
    progress_id: int = None,
    cursor: str = None,  # 途中再開用: 最後に処理したdelivery_item_id
) -> Delivery:
    """
    プランの配信を実行する。

    target_user_id: 指定時は単体送信
    
    配信パターン:
    ============
    
    【まとめて送信OFF】
    - 質問なし + 外部データなし     → 5件, GPT 1回 (全員同じ内容)
    - 質問なし + 外部データあり     → 5件, GPT 1回 (全員同じ内容)
    - 質問なし + 外部データ分割あり → 15件, GPT 3回 (分割×ユーザー)
    - 質問あり + 外部データなし     → 5件, GPT 5回 (ユーザーごと)
    - 質問あり + 外部データあり     → 5件, GPT 5回 (ユーザーごと)
    - 質問あり + 外部データ分割あり → 15件, GPT 15回 (分割×ユーザー)
    
    【まとめて送信ON】（外部データ分割ありの時のみ効果あり）
    - 質問なし + 外部データ分割あり → 5件, GPT 3回 (分割を1メールにまとめる)
    - 質問あり + 外部データ分割あり → 5件, GPT 15回 (分割を1メールにまとめる)
    """
    # 対象ユーザー取得
    users = _get_target_users(db, plan.id, target_user_id)
    if not users:
        logger.info(f"配信対象ユーザーなし: plan_id={plan.id}")
        return None

    # cursor再開: 指定されたuser_id以降から処理を再開
    original_count = len(users)
    if cursor:
        try:
            cursor_id = int(cursor)
            users = [u for u in users if u.id > cursor_id]
            logger.info(f"Cursor再開: user_id>{cursor_id}、{len(users)}/{original_count}件を処理")
        except ValueError:
            logger.warning(f"無効なcursor値: {cursor}、最初から処理")

    # 質問定義取得
    questions = db.query(PlanQuestion).filter(PlanQuestion.plan_id == plan.id).order_by(PlanQuestion.sort_order).all()

    # 外部データ取得
    external_setting = db.query(PlanExternalDataSetting).filter(
        PlanExternalDataSetting.plan_id == plan.id
    ).first()

    external_data_str = ""
    split_items = []
    if external_setting:
        firebase_key_enc = _get_firebase_credential(db, external_setting)
        if firebase_key_enc:
            external_data_str, split_items = load_external_data(
                external_setting.external_data_path,
                firebase_key_enc,
            )

    # 同じプランの実行中deliveryがあれば停止する
    stale = db.query(Delivery).filter(
        Delivery.plan_id == plan.id,
        Delivery.status == "running",
    ).all()
    for s in stale:
        s.status = "stopped"
        s.completed_at = datetime.now(JST)
    if stale:
        db.commit()

    # 配信件数を計算（total_count）
    if split_items and not plan.batch_send_enabled:
        # 分割あり + まとめてOFF → 分割×ユーザー
        total_count = len(split_items) * len(users)
    else:
        total_count = len(users)

    # Delivery レコード作成
    delivery = Delivery(
        plan_id=plan.id,
        send_type=send_type,
        status="running",
        total_count=total_count,
        started_at=datetime.now(JST),
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)

    # ProgressPlanにdelivery_idとstatusを即座に設定（進捗表示のため）
    if progress_id:
        from app.models.progress_plan import ProgressPlan
        progress = db.query(ProgressPlan).filter(ProgressPlan.id == progress_id).first()
        if progress:
            now = datetime.now(JST)
            logger.info(f"ProgressPlan更新: id={progress_id}, delivery_id={delivery.id}, status=1")
            progress.delivery_id = delivery.id
            progress.status = 1  # 実行中
            progress.heartbeat_at = now
            progress.updated_at = now
            db.commit()
        else:
            logger.warning(f"ProgressPlan not found: id={progress_id}")
    else:
        logger.debug(f"progress_id is None, skipping ProgressPlan update")

    prompt = prompt_override or plan.prompt
    summary_setting = get_summary_setting(db, plan.id)
    has_user_vars = _has_user_variables(prompt, questions)
    has_split_data = bool(split_items)

    success_count = 0
    fail_count = 0

    if plan.batch_send_enabled and has_split_data:
        # =================================================
        # まとめて送信モード: 分割を1メールにまとめる
        # =================================================
        logger.info(f"まとめて送信モード: plan_id={plan.id}, users={len(users)}, splits={len(split_items)}")
        
        # 質問なしの場合: 分割ごとのGPT結果をキャッシュ
        split_gpt_cache = {}  # item_name -> gpt_result
        
        for user in users:
            # 緊急停止チェック
            if check_emergency_stop():
                logger.warning(f"緊急停止により配信中断: delivery_id={delivery.id}")
                delivery.status = "stopped"
                delivery.completed_at = datetime.now(JST)
                db.commit()
                return delivery

            user_answers = db.query(UserAnswer).filter(UserAnswer.user_id == user.id).all()
            answers_dict = _build_answers_with_fallback(db, user.id, plan.id, questions, user_answers)

            all_contents = []
            
            for item_name, item_data in split_items:
                if has_user_vars:
                    # 質問あり: ユーザーごとにGPT生成
                    user_prompt = prompt
                    if summary_setting:
                        summaries = get_recent_summaries(
                            db, plan.id, user.id, summary_setting.summary_inject_count
                        )
                        user_prompt = inject_summaries_into_prompt(user_prompt, summaries)

                    resolved_prompt = resolve_variables(
                        text=user_prompt,
                        external_data=item_data,
                        item_name=item_name,
                        answers=answers_dict,
                        user_name=f"{user.name_last} {user.name_first}",
                        name_last=user.name_last,
                        name_first=user.name_first,
                    )

                    try:
                        gpt_result = generate_email_content(
                            prompt=resolved_prompt,
                            model=plan.model,
                            system_prompt=plan.system_prompt,
                            api_key=api_key,
                        )
                        all_contents.append((item_name, gpt_result))
                    except Exception as e:
                        logger.error(f"GPT生成失敗 (batch user={user.id}, item={item_name}): {e}")
                else:
                    # 質問なし: キャッシュから取得 or GPT生成
                    if item_name not in split_gpt_cache:
                        resolved_prompt = resolve_variables(
                            text=prompt,
                            external_data=item_data,
                            item_name=item_name,
                        )
                        try:
                            gpt_result = generate_email_content(
                                prompt=resolved_prompt,
                                model=plan.model,
                                system_prompt=plan.system_prompt,
                                api_key=api_key,
                            )
                            split_gpt_cache[item_name] = gpt_result
                        except Exception as e:
                            logger.error(f"GPT生成失敗 (batch item={item_name}): {e}")
                            split_gpt_cache[item_name] = None  # 失敗をマーク
                    
                    cached = split_gpt_cache.get(item_name)
                    if cached is None:
                        continue  # 失敗済みアイテムはスキップ
                    all_contents.append((item_name, cached))

            if not all_contents:
                # 全分割アイテムでGPT生成失敗
                fail_count += 1
                delivery.fail_count = fail_count
                _create_delivery_item(
                    db, delivery.id, user,
                    document_key="batch",
                    status=3,
                    error_msg="全分割アイテムでGPT生成失敗",
                )
                db.commit()
                continue

            # 分割コンテンツを結合
            combined_result = _combine_gpt_results(all_contents)
            
            ok = _send_email_with_retry(
                db=db,
                delivery=delivery,
                plan=plan,
                user=user,
                gpt_result=combined_result,
                document_key="batch",
                summary_setting=summary_setting,
                api_key=api_key,
            )
            if ok:
                success_count += 1
                delivery.success_count = success_count
            else:
                fail_count += 1
                delivery.fail_count = fail_count
            db.commit()

            # Heartbeat更新（Watchdog対策）
            if (success_count + fail_count) % HEARTBEAT_INTERVAL == 0:
                _update_progress_heartbeat(db, progress_id, cursor=str(user.id))

            time.sleep(throttle_seconds)

    elif has_split_data:
        # =================================================
        # 分割あり + まとめてOFF: 分割×ユーザー件のメール
        # =================================================
        logger.info(f"分割送信モード: plan_id={plan.id}, users={len(users)}, splits={len(split_items)}")
        
        for item_name, item_data in split_items:
            if has_user_vars:
                # 質問あり: ユーザーごとにGPT生成
                for user in users:
                    # 緊急停止チェック
                    if check_emergency_stop():
                        logger.warning(f"緊急停止により配信中断: delivery_id={delivery.id}")
                        delivery.status = "stopped"
                        delivery.completed_at = datetime.now(JST)
                        db.commit()
                        return delivery

                    user_answers = db.query(UserAnswer).filter(UserAnswer.user_id == user.id).all()
                    answers_dict = _build_answers_with_fallback(db, user.id, plan.id, questions, user_answers)

                    user_prompt = prompt
                    if summary_setting:
                        summaries = get_recent_summaries(
                            db, plan.id, user.id, summary_setting.summary_inject_count
                        )
                        user_prompt = inject_summaries_into_prompt(user_prompt, summaries)

                    resolved_prompt = resolve_variables(
                        text=user_prompt,
                        external_data=item_data,
                        item_name=item_name,
                        answers=answers_dict,
                        user_name=f"{user.name_last} {user.name_first}",
                        name_last=user.name_last,
                        name_first=user.name_first,
                    )

                    ok = _send_with_retry(
                        db=db,
                        delivery=delivery,
                        plan=plan,
                        user=user,
                        resolved_prompt=resolved_prompt,
                        document_key=item_name,
                        summary_setting=summary_setting,
                        api_key=api_key,
                    )
                    if ok:
                        success_count += 1
                        delivery.success_count = success_count
                    else:
                        fail_count += 1
                        delivery.fail_count = fail_count
                    db.commit()

                    if (success_count + fail_count) % HEARTBEAT_INTERVAL == 0:
                        _update_progress_heartbeat(db, progress_id, cursor=str(user.id))

                    time.sleep(throttle_seconds)
            else:
                # 質問なし: 分割ごとに1回GPT → 全ユーザーに送信
                resolved_prompt = resolve_variables(
                    text=prompt,
                    external_data=item_data,
                    item_name=item_name,
                )

                try:
                    gpt_result = generate_email_content(
                        prompt=resolved_prompt,
                        model=plan.model,
                        system_prompt=plan.system_prompt,
                        api_key=api_key,
                    )
                except Exception as e:
                    logger.error(f"GPT生成失敗 (split item={item_name}): {e}")
                    # この分割アイテムの全ユーザーを失敗扱い
                    for user in users:
                        fail_count += 1
                        delivery.fail_count = fail_count
                        _create_delivery_item(
                            db, delivery.id, user,
                            document_key=item_name,
                            status=3,
                            error_msg=f"GPT生成失敗: {e}",
                        )
                    db.commit()
                    continue

                for user in users:
                    # 緊急停止チェック
                    if check_emergency_stop():
                        logger.warning(f"緊急停止により配信中断: delivery_id={delivery.id}")
                        delivery.status = "stopped"
                        delivery.completed_at = datetime.now(JST)
                        db.commit()
                        return delivery

                    ok = _send_email_with_retry(
                        db=db,
                        delivery=delivery,
                        plan=plan,
                        user=user,
                        gpt_result=gpt_result,
                        document_key=item_name,
                        summary_setting=summary_setting,
                        api_key=api_key,
                    )
                    if ok:
                        success_count += 1
                        delivery.success_count = success_count
                    else:
                        fail_count += 1
                        delivery.fail_count = fail_count
                    db.commit()

                    if (success_count + fail_count) % HEARTBEAT_INTERVAL == 0:
                        _update_progress_heartbeat(db, progress_id, cursor=str(user.id))

                    time.sleep(throttle_seconds)

    elif has_user_vars:
        # =================================================
        # 分割なし + 質問あり: ユーザーごとにGPT
        # =================================================
        logger.info(f"個別送信モード（質問あり）: plan_id={plan.id}, users={len(users)}")
        
        for user in users:
            # 緊急停止チェック
            if check_emergency_stop():
                logger.warning(f"緊急停止により配信中断: delivery_id={delivery.id}")
                delivery.status = "stopped"
                delivery.completed_at = datetime.now(JST)
                db.commit()
                return delivery

            user_answers = db.query(UserAnswer).filter(UserAnswer.user_id == user.id).all()
            answers_dict = _build_answers_with_fallback(db, user.id, plan.id, questions, user_answers)

            user_prompt = prompt
            if summary_setting:
                summaries = get_recent_summaries(
                    db, plan.id, user.id, summary_setting.summary_inject_count
                )
                user_prompt = inject_summaries_into_prompt(user_prompt, summaries)

            resolved_prompt = resolve_variables(
                text=user_prompt,
                external_data=external_data_str or None,
                answers=answers_dict,
                user_name=f"{user.name_last} {user.name_first}",
                name_last=user.name_last,
                name_first=user.name_first,
            )

            ok = _send_with_retry(
                db=db,
                delivery=delivery,
                plan=plan,
                user=user,
                resolved_prompt=resolved_prompt,
                document_key=None,
                summary_setting=summary_setting,
                api_key=api_key,
            )
            if ok:
                success_count += 1
                delivery.success_count = success_count
            else:
                fail_count += 1
                delivery.fail_count = fail_count
            db.commit()

            if (success_count + fail_count) % HEARTBEAT_INTERVAL == 0:
                _update_progress_heartbeat(db, progress_id, cursor=str(user.id))

            time.sleep(throttle_seconds)

    else:
        # =================================================
        # 分割なし + 質問なし: GPT 1回 → 全員に同じ内容
        # =================================================
        logger.info(f"共通送信モード: plan_id={plan.id}, users={len(users)}")
        
        resolved_prompt = resolve_variables(
            text=prompt,
            external_data=external_data_str or None,
        )

        try:
            gpt_result = generate_email_content(
                prompt=resolved_prompt,
                model=plan.model,
                system_prompt=plan.system_prompt,
                api_key=api_key,
            )
        except Exception as e:
            logger.error(f"GPT生成失敗: {e}")
            # 全ユーザーのDeliveryItemを失敗で作成
            for user in users:
                _create_delivery_item(
                    db, delivery.id, user,
                    document_key=None,
                    status=3,
                    error_msg=f"GPT生成失敗: {e}",
                )
            delivery.status = "failed"
            delivery.fail_count = len(users)
            delivery.completed_at = datetime.now(JST)
            db.commit()
            return delivery

        for user in users:
            # 緊急停止チェック
            if check_emergency_stop():
                logger.warning(f"緊急停止により配信中断: delivery_id={delivery.id}")
                delivery.status = "stopped"
                delivery.completed_at = datetime.now(JST)
                db.commit()
                return delivery

            ok = _send_email_with_retry(
                db=db,
                delivery=delivery,
                plan=plan,
                user=user,
                gpt_result=gpt_result,
                document_key=None,
                summary_setting=summary_setting,
                api_key=api_key,
            )
            if ok:
                success_count += 1
                delivery.success_count = success_count
            else:
                fail_count += 1
                delivery.fail_count = fail_count
            db.commit()

            if (success_count + fail_count) % HEARTBEAT_INTERVAL == 0:
                _update_progress_heartbeat(db, progress_id, cursor=str(user.id))

            time.sleep(throttle_seconds)

    # Delivery完了更新
    delivery.success_count = success_count
    delivery.fail_count = fail_count
    delivery.completed_at = datetime.now(JST)
    if fail_count == 0:
        delivery.status = "success"
    elif success_count == 0:
        delivery.status = "failed"
    else:
        delivery.status = "partial_failed"

    db.commit()
    logger.info(f"配信完了: delivery_id={delivery.id}, success={success_count}, fail={fail_count}")
    return delivery


def _combine_gpt_results(contents: list) -> dict:
    """複数のGPT結果を1つに結合する
    
    Args:
        contents: [(item_name, gpt_result), ...]
    
    Returns:
        結合されたgpt_result {"subject": ..., "body": ...}
    """
    if not contents:
        return {"subject": "", "body": ""}
    
    # 件名は最初の結果を使用
    subject = contents[0][1]["subject"]
    
    # 本文は区切り線で結合
    bodies = []
    for item_name, gpt_result in contents:
        bodies.append(f"【{item_name}】\n{gpt_result['body']}")
    
    combined_body = "\n\n---\n\n".join(bodies)
    
    return {"subject": subject, "body": combined_body}


def _get_target_users(db: Session, plan_id: int, target_user_id: int = None) -> list[User]:
    """配信対象ユーザーを取得（id昇順でソート）"""
    q = db.query(User).join(
        Subscription, Subscription.user_id == User.id
    ).filter(
        Subscription.plan_id == plan_id,
        Subscription.status.in_(["trialing", "active", "admin_added"]),
        User.is_active == True,
        User.deliverable == True,
        User.email_verified == True,
    )
    if target_user_id:
        q = q.filter(User.id == target_user_id)
    return q.order_by(User.id.asc()).all()  # cursor再開のためid昇順必須


def _create_delivery_item(
    db: Session,
    delivery_id: int,
    user: User,
    document_key: str = None,
    status: int = 0,
    retry_count: int = 0,
    resend_message_id: str = None,
    error_msg: str = None,
):
    """DeliveryItemレコード作成"""
    item = DeliveryItem(
        delivery_id=delivery_id,
        user_id=user.id,
        member_no_snapshot=user.member_no,
        document_key=document_key,
        status=status,
        retry_count=retry_count,
        resend_message_id=resend_message_id,
        last_error_message=error_msg,
        sent_at=datetime.now(JST) if status == 2 else None,
    )
    db.add(item)
    db.commit()


def _log_event(
    db: Session,
    level: str,
    event_type: str,
    plan_id: int = None,
    user_id: int = None,
    member_no: str = None,
    delivery_id: int = None,
    message: str = "",
):
    """システムログ記録"""
    log = SystemLog(
        level=level,
        event_type=event_type,
        plan_id=plan_id,
        user_id=user_id,
        member_no_snapshot=member_no,
        delivery_id=delivery_id,
        message=message,
    )
    db.add(log)
    db.commit()


def _build_answers_with_fallback(
    db: Session, user_id: int, plan_id: int, questions: list, user_answers: list,
) -> dict:
    """回答辞書を構築 (同一 var_name の他プラン回答をフォールバック)"""
    answer_map = {a.question_id: a.answer_value for a in user_answers}
    result = {}

    for q in questions:
        raw_value = answer_map.get(q.id, "")

        # フォールバック: 未回答なら他プランの同一 var_name の回答を探す
        if not raw_value and q.var_name:
            other = db.query(UserAnswer).join(
                PlanQuestion, UserAnswer.question_id == PlanQuestion.id
            ).filter(
                UserAnswer.user_id == user_id,
                PlanQuestion.var_name == q.var_name,
                PlanQuestion.plan_id != plan_id,
                UserAnswer.answer_value != None,
                UserAnswer.answer_value != "",
            ).first()
            if other:
                raw_value = other.answer_value

        if q.question_type in ("checkbox", "array") and raw_value:
            try:
                parsed = json.loads(raw_value)
                result[q.var_name] = parsed
            except (json.JSONDecodeError, TypeError):
                result[q.var_name] = raw_value
        else:
            result[q.var_name] = raw_value or ""

    return result


def _get_firebase_credential(db: Session, external_setting: PlanExternalDataSetting) -> Optional[str]:
    """外部データ設定からFirebase認証情報(暗号化済み)を取得"""
    # 1. firebase_credential_id がある場合
    if external_setting.firebase_credential_id:
        credential = db.query(FirebaseCredential).filter(
            FirebaseCredential.id == external_setting.firebase_credential_id
        ).first()
        if credential:
            return credential.encrypted_json
    # 2. 後方互換: firebase_key_json_enc
    if external_setting.firebase_key_json_enc:
        return external_setting.firebase_key_json_enc
    return None


# =========================================================
# リトライ付き送信関数
# =========================================================

def _send_with_retry(
    db: Session,
    delivery: Delivery,
    plan: Plan,
    user: User,
    resolved_prompt: str,
    document_key: str,
    summary_setting,
    api_key: str,
) -> bool:
    """GPT生成 + メール送信をリトライ付きで実行（通常モード・ハイブリッドモード用）"""
    from app.services.report_service import send_error_alert

    last_error = None

    for attempt in range(MAX_RETRY + 1):
        try:
            gpt_result = generate_email_content(
                prompt=resolved_prompt,
                model=plan.model,
                system_prompt=plan.system_prompt,
                api_key=api_key,
            )

            # メール送信
            ok, error_msg = _try_send_email(
                db, delivery, plan, user,
                gpt_result, document_key, summary_setting, api_key,
            )
            if ok:
                # 成功: delivery_item作成
                _create_delivery_item(
                    db, delivery.id, user,
                    document_key=document_key,
                    status=2,
                    retry_count=attempt,
                )
                return True

            last_error = error_msg

        except Exception as e:
            last_error = str(e)

        # リトライ
        if attempt < MAX_RETRY:
            logger.warning(f"送信リトライ {attempt + 1}/{MAX_RETRY}: user_id={user.id} - {last_error}")
            time.sleep(2 ** attempt)  # 1, 2, 4秒

    # 全リトライ失敗
    logger.error(f"送信失敗 (リトライ上限): user_id={user.id} - {last_error}")
    _create_delivery_item(
        db, delivery.id, user,
        document_key=document_key,
        status=3,
        retry_count=MAX_RETRY,
        error_msg=last_error,
    )
    _log_event(db, "ERROR", "send_failed_after_retry", plan.id, user.id, user.member_no, delivery.id, last_error)

    # エラー通知
    try:
        send_error_alert(
            plan_id=plan.id,
            plan_name=plan.name,
            error_message=f"リトライ上限到達 ({MAX_RETRY}回): {last_error}",
            details={
                "user_id": user.id,
                "member_no": user.member_no,
                "email": user.email,
            }
        )
    except Exception as alert_err:
        logger.error(f"エラー通知送信失敗: {alert_err}")

    return False


def _send_email_with_retry(
    db: Session,
    delivery: Delivery,
    plan: Plan,
    user: User,
    gpt_result: dict,
    document_key: str,
    summary_setting,
    api_key: str,
) -> bool:
    """メール送信のみリトライ付きで実行（バッチモード用、GPT結果は事前生成済み）"""
    from app.services.report_service import send_error_alert

    last_error = None

    for attempt in range(MAX_RETRY + 1):
        ok, error_msg = _try_send_email(
            db, delivery, plan, user,
            gpt_result, document_key, summary_setting, api_key,
        )
        if ok:
            _create_delivery_item(
                db, delivery.id, user,
                document_key=document_key,
                status=2,
                retry_count=attempt,
            )
            return True

        last_error = error_msg

        if attempt < MAX_RETRY:
            logger.warning(f"メール送信リトライ {attempt + 1}/{MAX_RETRY}: user_id={user.id} - {last_error}")
            time.sleep(2 ** attempt)

    # 全リトライ失敗
    logger.error(f"メール送信失敗 (リトライ上限): user_id={user.id} - {last_error}")
    _create_delivery_item(
        db, delivery.id, user,
        document_key=document_key,
        status=3,
        retry_count=MAX_RETRY,
        error_msg=last_error,
    )
    _log_event(db, "ERROR", "send_failed_after_retry", plan.id, user.id, user.member_no, delivery.id, last_error)

    try:
        send_error_alert(
            plan_id=plan.id,
            plan_name=plan.name,
            error_message=f"リトライ上限到達 ({MAX_RETRY}回): {last_error}",
            details={
                "user_id": user.id,
                "member_no": user.member_no,
                "email": user.email,
            }
        )
    except Exception as alert_err:
        logger.error(f"エラー通知送信失敗: {alert_err}")

    return False


def _try_send_email(
    db: Session,
    delivery: Delivery,
    plan: Plan,
    user: User,
    gpt_result: dict,
    document_key: str,
    summary_setting,
    api_key: str,
) -> tuple[bool, str]:
    """メール送信を試行（delivery_item作成なし）。戻り値: (成功, エラーメッセージ)"""
    subject = gpt_result["subject"]
    body = gpt_result["body"]

    # ユーザー個別変数を置換
    body = resolve_variables(
        text=body,
        user_name=f"{user.name_last} {user.name_first}",
        name_last=user.name_last,
        name_first=user.name_first,
    )
    subject = resolve_variables(
        text=subject,
        user_name=f"{user.name_last} {user.name_first}",
        name_last=user.name_last,
        name_first=user.name_first,
    )

    # 配信停止URL
    unsubscribe_url = None
    if user.unsubscribe_token:
        unsubscribe_url = f"{settings.SITE_URL}/api/me/unsubscribe?token={user.unsubscribe_token}"

    try:
        result = send_email(
            to_email=user.email,
            subject=subject,
            body=body,
            unsubscribe_url=unsubscribe_url,
            api_key=api_key,
        )

        # 件名をDeliveryに保存 (初回のみ)
        if not delivery.subject:
            delivery.subject = subject
            db.commit()

        # あらすじ生成
        if summary_setting:
            generate_and_save_summary(
                db, plan.id, user.id, body, summary_setting,
                model=plan.model, api_key=api_key,
            )

        return True, ""

    except Exception as e:
        return False, str(e)


# =========================================================
# 失敗分再送機能
# =========================================================

def retry_failed_delivery(db: Session, delivery_id: int, api_key: str = None) -> dict:
    """失敗したdelivery_itemのユーザーにのみ再送"""
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id).first()
    if not delivery:
        return {"error": "Delivery not found"}

    plan = db.query(Plan).filter(Plan.id == delivery.plan_id).first()
    if not plan:
        return {"error": "Plan not found"}

    # 失敗したdelivery_items取得
    failed_items = db.query(DeliveryItem).filter(
        DeliveryItem.delivery_id == delivery_id,
        DeliveryItem.status == 3,
    ).all()

    if not failed_items:
        return {"message": "No failed items to retry", "retried": 0, "success": 0, "failed": 0}

    # 質問定義・外部データ・サマリー設定を取得
    questions = db.query(PlanQuestion).filter(PlanQuestion.plan_id == plan.id).order_by(PlanQuestion.sort_order).all()

    external_setting = db.query(PlanExternalDataSetting).filter(
        PlanExternalDataSetting.plan_id == plan.id
    ).first()

    external_data_str = ""
    if external_setting:
        firebase_key_enc = _get_firebase_credential(db, external_setting)
        if firebase_key_enc:
            external_data_str, _ = load_external_data(
                external_setting.external_data_path,
                firebase_key_enc,
            )

    summary_setting = get_summary_setting(db, plan.id)

    success_count = 0
    fail_count = 0

    for item in failed_items:
        user = db.query(User).filter(User.id == item.user_id).first()
        if not user:
            continue

        # ユーザーが配信対象かチェック
        if not user.is_active or not user.deliverable or not user.email_verified:
            continue

        # プロンプト生成
        user_answers = db.query(UserAnswer).filter(UserAnswer.user_id == user.id).all()
        answers_dict = _build_answers_with_fallback(db, user.id, plan.id, questions, user_answers)

        user_prompt = plan.prompt
        if summary_setting:
            summaries = get_recent_summaries(
                db, plan.id, user.id, summary_setting.summary_inject_count
            )
            user_prompt = inject_summaries_into_prompt(user_prompt, summaries)

        resolved_prompt = resolve_variables(
            text=user_prompt,
            external_data=external_data_str or None,
            answers=answers_dict,
            user_name=f"{user.name_last} {user.name_first}",
            name_last=user.name_last,
            name_first=user.name_first,
        )

        # リトライ送信
        ok = _send_with_retry(
            db=db,
            delivery=delivery,
            plan=plan,
            user=user,
            resolved_prompt=resolved_prompt,
            document_key=item.document_key,
            summary_setting=summary_setting,
            api_key=api_key,
        )

        if ok:
            # 元のfailed itemを削除（新しいitemが作成されている）
            db.delete(item)
            db.commit()
            success_count += 1
        else:
            fail_count += 1

        time.sleep(5)  # スロットリング

    # delivery統計を更新
    delivery.success_count = (delivery.success_count or 0) + success_count
    delivery.fail_count = max(0, (delivery.fail_count or 0) - success_count)
    if delivery.fail_count == 0:
        delivery.status = "success"
    elif delivery.success_count > 0:
        delivery.status = "partial_failed"
    db.commit()

    return {
        "message": "Retry completed",
        "retried": len(failed_items),
        "success": success_count,
        "failed": fail_count,
    }
