"""OpenAI API サービス (subject + body JSON生成)"""
import json
from openai import OpenAI
from app.core.api_keys import get_openai_api_key
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_SYSTEM_PROMPT = """あなたはメールコンテンツ生成AIです。
以下の形式でJSON応答してください:
{"subject": "メール件名", "body": "メール本文"}
bodyはHTMLタグなしのプレーンテキストで記述してください。"""


def generate_email_content(
    prompt: str,
    model: str = "gpt-4o-mini",
    system_prompt: str = None,
    api_key: str = None,
    timeout_read: int = 240,
    max_retries: int = 3,
) -> dict:
    """
    GPTでメールコンテンツを生成。
    Returns: {"subject": "...", "body": "..."}
    """
    client = OpenAI(
        api_key=api_key or get_openai_api_key(),
        timeout=timeout_read,
    )

    system_msg = system_prompt or DEFAULT_SYSTEM_PROMPT

    # response_format=json_object 使用時、messagesに"json"が必須
    if "json" not in system_msg.lower() and "json" not in prompt.lower():
        system_msg += '\n\n回答は必ず {"subject": "件名", "body": "本文"} のJSON形式で出力してください。'

    # temperatureをサポートしないモデル（o1系, o3系, gpt-5等）を判定
    extra_params = {}
    model_lower = (model or "").lower()
    if not any(model_lower.startswith(p) for p in ("o1", "o3", "gpt-5")):
        extra_params["temperature"] = 0.7

    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                **extra_params,
            )

            content = response.choices[0].message.content
            result = json.loads(content)

            if "subject" not in result or "body" not in result:
                raise ValueError(f"GPT応答に必須フィールドがありません: {list(result.keys())}")

            logger.info(f"GPTコンテンツ生成成功: model={model}, subject={result['subject'][:30]}")
            return result

        except Exception as e:
            # temperatureエラーの場合、パラメータを除外してリトライ
            if "temperature" in str(e) and "temperature" in extra_params:
                logger.warning(f"temperature非対応モデル検出 ({model}), パラメータ除外してリトライ")
                extra_params.pop("temperature", None)
                continue
            last_error = e
            logger.warning(f"GPT生成リトライ {attempt + 1}/{max_retries}: {e}")

    logger.error(f"GPT生成失敗 ({max_retries}回リトライ後): {last_error}")
    raise last_error
