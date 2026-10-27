"""Public consultation protocol and pricing."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import hmac
import json
import re
import secrets

WECHAT_ID = "bxzgf-bxbgf"
NATAL_PRICE = "18.88"
LUCK_PRICE = "36.88"
PERIOD_FEE = "2"
PLANS = (
    {"id": "natal_v7", "title": "原局解读", "price": NATAL_PRICE, "description": "原局八步解读，分别说明事业学业、财富资源、感情合作，并附推导依据。"},
    {"id": "luck_v7", "title": "原局＋大运", "price": LUCK_PRICE, "description": "原局、前六步大运及流年趋势，包含逐年评分与子平K线。"},
    {"id": "date_v7", "title": "原局＋大运＋指定年月日详解", "price": f"{LUCK_PRICE}＋年/月/日各{PERIOD_FEE}元/次", "description": "基础报告上按需追加：仅分析年、仅分析月或仅分析日，每项2元/次，可反复选择。"},
)
PLAN_NAMES = {"natal": "原局解读（旧版）", "annual": "大运流年（旧版）", "daily": "运年月日详解（旧版）",
              **{p["id"]: p["title"] for p in PLANS}, "date_addon_v7": "大运年月日追加详解"}


def consultation_details(value=None):
    """Keep the chosen period and optional private reference; never payment fields."""
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value)-{"date", "parent_id", "scope"}:
        raise ReferralError("咨询补充信息不正确。")
    result = {}
    if value.get("date"):
        from datetime import date
        try:
            result["date"] = date.fromisoformat(value["date"]).isoformat()
        except (TypeError, ValueError):
            raise ReferralError("指定日期不正确。") from None
    if value.get("parent_id"):
        parent = str(value["parent_id"]).strip().upper()
        if not re.fullmatch(r"ZP[A-F0-9]{12}", parent):
            raise ReferralError("请填写原局大运基础咨询编号（ZP开头）。")
        result["parent_id"] = parent
    if value.get("scope"):
        scope = value["scope"]
        if not isinstance(scope, str) or not 1 <= len(scope) <= 240 or any(ord(char) < 32 for char in scope):
            raise ReferralError("解读范围不正确，请重新选择大运与年月日。")
        result["scope"] = scope
    return result
GRADE_RATES = {"C": 2000, "B": 3000, "A": 4000}
B_THRESHOLD = 50000
A_REVIEW_THRESHOLD = 300000


class ReferralError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier(prefix: str) -> str:
    return prefix + secrets.token_hex(6).upper()


def money_cents(value: str) -> int:
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or not 0 <= amount <= 100000 or amount != amount.quantize(Decimal(".01")):
            raise ValueError
        return int(amount * 100)
    except (ValueError, InvalidOperation, OverflowError):
        raise ReferralError("请输入 0 至 100000 元的有效金额，最多两位小数。") from None


def commission(cents: int, rate: int) -> int:
    return int((Decimal(cents) * rate / 10000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def username(value: str) -> str:
    value = str(value).strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", value):
        raise ReferralError("登录名需为 3 至 32 位英文字母、数字、点、横线或下划线。")
    return value


def password_hash(password: str) -> str:
    if not 10 <= len(password) <= 256:
        raise ReferralError("密码长度需为 10 至 256 个字符。")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"


def password_matches(password: str, encoded: str) -> bool:
    if not re.fullmatch(r"pbkdf2_sha256\$600000\$[a-f0-9]{32}\$[a-f0-9]{64}", encoded) or len(password) > 256:
        return False
    _, _, salt, expected = encoded.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000).hex()
    return hmac.compare_digest(actual, expected)


def parse_document(raw: bytes, format_name: str) -> dict:
    if len(raw) > 4 * 1024 * 1024:
        raise ReferralError("资料文件超过 4MB，请分批导出。")
    def reject_constant(value):
        raise ValueError(value)
    try:
        data = json.loads(raw.decode("utf-8-sig"), parse_constant=reject_constant)
    except (ValueError, UnicodeError):
        raise ReferralError("资料不是有效的 UTF-8 JSON 文件。") from None
    if not isinstance(data, dict) or data.get("format") != format_name:
        raise ReferralError("资料类型不匹配，请使用相应的导出文件。")
    return data
