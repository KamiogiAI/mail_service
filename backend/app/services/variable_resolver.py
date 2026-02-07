"""変数置換エンジン (置換順序厳守)"""
import json
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


def resolve_variables(
    text: str,
    external_data: Optional[str] = None,
    item_name: Optional[str] = None,
    answers: Optional[dict] = None,
    user_name: Optional[str] = None,
    name_last: Optional[str] = None,
    name_first: Optional[str] = None,
) -> str:
    """
    変数を順序通りに置換する。

    置換順序:
    1. {external_data} - 外部データ
    2. {~} - 分割時のitem_name
    3. {var_name} - 質問回答 (plan_questionsのvar_name)
    4. {name} - フルネーム
    5. {name-l}, {name-f} - 姓/名
    """
    result = text

    # 1. 外部データ
    if external_data is not None:
        result = result.replace("{external_data}", external_data)

    # 2. 分割アイテム名
    if item_name is not None:
        result = result.replace("{~}", item_name)

    # 3. 質問回答
    if answers:
        for var_name, value in answers.items():
            # 値がリストの場合はJSON文字列にしない
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            elif isinstance(value, dict):
                value = json.dumps(value, ensure_ascii=False, indent=2)
            result = result.replace("{" + var_name + "}", str(value))

    # 4. フルネーム
    if user_name is not None:
        result = result.replace("{name}", user_name)

    # 5. 姓/名
    if name_last is not None:
        result = result.replace("{name-l}", name_last)
    if name_first is not None:
        result = result.replace("{name-f}", name_first)

    return result


def build_answers_dict(
    questions: list,
    user_answers: list,
) -> dict:
    """
    質問定義とユーザー回答からvar_name→valueのdictを構築。
    questions: PlanQuestion のリスト
    user_answers: UserAnswer のリスト
    """
    answer_map = {a.question_id: a.answer_value for a in user_answers}
    result = {}
    for q in questions:
        raw_value = answer_map.get(q.id, "")
        # checkbox/arrayの場合はJSONパース
        if q.question_type in ("checkbox", "array") and raw_value:
            try:
                parsed = json.loads(raw_value)
                result[q.var_name] = parsed
            except (json.JSONDecodeError, TypeError):
                result[q.var_name] = raw_value
        else:
            result[q.var_name] = raw_value or ""
    return result
