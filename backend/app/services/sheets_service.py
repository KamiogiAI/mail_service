"""Google Sheets カスタム日付チェックサービス"""
import re
from datetime import datetime, date
import gspread
from google.oauth2.service_account import Credentials
from app.core.logging import get_logger

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def is_today_in_sheets(
    sheets_id: str,
    credentials_json: dict = None,
) -> bool:
    """
    Google Sheetsから日付リストを読み取り、JST「今日」と一致するか確認。

    シート名優先: 配信日程 → Sheet1 → シート1 → 先頭シート
    A1:A100 を読み取り、YYYY-MM-DD推奨 (複数フォーマット許容)
    """
    try:
        if credentials_json:
            creds = Credentials.from_service_account_info(credentials_json, scopes=SCOPES)
            gc = gspread.authorize(creds)
        else:
            # グローバルFirebase Keyフォールバック
            from app.core.api_keys import get_firebase_credentials
            global_creds = get_firebase_credentials()
            if global_creds:
                creds = Credentials.from_service_account_info(global_creds, scopes=SCOPES)
                gc = gspread.authorize(creds)
            else:
                gc = gspread.service_account()

        spreadsheet = gc.open_by_key(sheets_id)

        # シート名優先順
        worksheet = None
        for name in ["配信日程", "Sheet1", "シート1"]:
            try:
                worksheet = spreadsheet.worksheet(name)
                break
            except gspread.WorksheetNotFound:
                continue

        if worksheet is None:
            worksheet = spreadsheet.sheet1

        # A列の値を読み取り
        values = worksheet.col_values(1)[:100]

        # JST今日
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Asia/Tokyo")).date()

        for val in values:
            parsed = _parse_date(val)
            if parsed and parsed == today:
                return True

        return False

    except Exception as e:
        logger.error(f"Sheets日付チェックエラー: {sheets_id} - {e}")
        return False


def test_sheets_connection(
    sheets_id: str,
    credentials_json: dict = None,
) -> dict:
    """
    Google Sheets接続テスト。
    接続OK/NG、今日が対象か、日付一覧、シート名を返す。
    """
    try:
        if credentials_json:
            creds = Credentials.from_service_account_info(credentials_json, scopes=SCOPES)
            gc = gspread.authorize(creds)
        else:
            from app.core.api_keys import get_firebase_credentials
            global_creds = get_firebase_credentials()
            if global_creds:
                creds = Credentials.from_service_account_info(global_creds, scopes=SCOPES)
                gc = gspread.authorize(creds)
            else:
                gc = gspread.service_account()

        spreadsheet = gc.open_by_key(sheets_id)

        worksheet = None
        sheet_name = None
        for name in ["配信日程", "Sheet1", "シート1"]:
            try:
                worksheet = spreadsheet.worksheet(name)
                sheet_name = name
                break
            except gspread.WorksheetNotFound:
                continue

        if worksheet is None:
            worksheet = spreadsheet.sheet1
            sheet_name = worksheet.title

        values = worksheet.col_values(1)[:100]

        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Asia/Tokyo")).date()

        dates = []
        is_today = False
        for val in values:
            parsed = _parse_date(val)
            if parsed:
                dates.append(parsed.isoformat())
                if parsed == today:
                    is_today = True

        return {
            "ok": True,
            "sheet_name": sheet_name,
            "is_today": is_today,
            "today": today.isoformat(),
            "dates": dates,
        }

    except Exception as e:
        import traceback
        error_detail = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"Sheets接続テストエラー: {sheets_id} - {error_detail}")
        return {"ok": False, "error": str(e) or repr(e)}


def _parse_date(value: str) -> date:
    """複数フォーマットの日付パース"""
    if not value:
        return None

    value = value.strip()

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y年%m月%d日",
        "%m/%d/%Y",
        "%m-%d-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None
