"""あらすじ生成・保存・注入サービス"""
from sqlalchemy.orm import Session
from app.models.user_summary import UserSummary
from app.models.plan_summary_setting import PlanSummarySetting
from app.services.openai_service import generate_email_content
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_summary_setting(db: Session, plan_id: int) -> PlanSummarySetting:
    """あらすじ設定を取得"""
    return db.query(PlanSummarySetting).filter(
        PlanSummarySetting.plan_id == plan_id
    ).first()


def get_recent_summaries(db: Session, plan_id: int, user_id: int, count: int) -> list[str]:
    """最近のあらすじをcount件取得"""
    summaries = db.query(UserSummary).filter(
        UserSummary.plan_id == plan_id,
        UserSummary.user_id == user_id,
    ).order_by(UserSummary.created_at.desc()).limit(count).all()

    return [s.summary_text for s in reversed(summaries)]


def inject_summaries_into_prompt(prompt: str, summaries: list[str]) -> str:
    """あらすじをプロンプトに注入"""
    if not summaries:
        return prompt

    summary_block = "\n\n【これまでのあらすじ】\n"
    for i, s in enumerate(summaries, 1):
        summary_block += f"{i}. {s}\n"
    summary_block += "\n上記のあらすじの続きとして、新しい内容を生成してください。\n"

    return summary_block + "\n" + prompt


def generate_and_save_summary(
    db: Session,
    plan_id: int,
    user_id: int,
    email_body: str,
    summary_setting: PlanSummarySetting,
    model: str = "gpt-4o-mini",
    api_key: str = None,
):
    """メール本文からあらすじを生成して保存"""
    try:
        prompt = f"""{summary_setting.summary_prompt}

以下のメール本文を{summary_setting.summary_length_target}文字程度で要約してください:

---
{email_body}
---

要約のみを返してください。"""

        result = generate_email_content(
            prompt=prompt,
            model=model,
            system_prompt="あなたは要約AIです。JSON形式で {\"subject\": \"要約\", \"body\": \"要約テキスト\"} を返してください。",
            api_key=api_key,
        )

        summary_text = result.get("body", "")
        if not summary_text:
            return

        # 保存
        summary = UserSummary(
            plan_id=plan_id,
            user_id=user_id,
            summary_text=summary_text,
        )
        db.add(summary)

        # 最大件数制限
        existing_count = db.query(UserSummary).filter(
            UserSummary.plan_id == plan_id,
            UserSummary.user_id == user_id,
        ).count()

        if existing_count > summary_setting.summary_max_keep:
            # 古い順に削除
            old_summaries = db.query(UserSummary).filter(
                UserSummary.plan_id == plan_id,
                UserSummary.user_id == user_id,
            ).order_by(UserSummary.created_at.asc()).limit(
                existing_count - summary_setting.summary_max_keep
            ).all()
            for old in old_summaries:
                db.delete(old)

        db.commit()
        logger.info(f"あらすじ保存: plan_id={plan_id}, user_id={user_id}")

    except Exception as e:
        logger.error(f"あらすじ生成エラー: plan_id={plan_id}, user_id={user_id} - {e}")
