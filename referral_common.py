"""Public protocol and pricing. No access to the administrator ledger."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import hmac
import json
import re
import secrets

WECHAT_ID = "bxzgf-bxbgf"
PLANS = (
    {"id": "natal", "title": "原局解读", "price": "8.88", "description": "原局八步分析，结合古籍梳理旺衰、格局与取用。"},
    {"id": "annual", "title": "大运流年", "price": "28.88", "description": "原局、前六步大运详解与评分K线，再详解选定流年。"},
    {"id": "daily", "title": "运年月日详解", "price": "36.88", "description": "原局、前六步大运与评分K线，再详解选定流年、流月、流日。"},
)
PLAN_NAMES = {p["id"]: p["title"] for p in PLANS}
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
