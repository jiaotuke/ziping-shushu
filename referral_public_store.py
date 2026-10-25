"""Public leads and agent login/read views. No access to the private ledger."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3

from runtime_paths import DATA_ROOT
from referral_common import ReferralError, PLAN_NAMES, GRADE_RATES, now, identifier, username, password_hash, password_matches


class PublicStore:
    def __init__(self, *, demo: bool = False, root: Path | None = None, maintenance: bool = False):
        if demo and not maintenance and os.environ.get("ZIPING_ALLOW_REFERRAL_DEMO") != "1":
            raise ReferralError("此网站未启用演示身份。")
        self.demo = bool(demo)
        self.maintenance = bool(maintenance)
        self.root = root or Path(os.environ.get("ZIPING_PUBLIC_DATA") or DATA_ROOT / ".local" / "public-site")
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / ("public-demo.sqlite3" if demo else "public-live.sqlite3")
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    code TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL, credential_version TEXT NOT NULL, grade TEXT NOT NULL,
                    enabled INTEGER NOT NULL, must_change_password INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (digest TEXT PRIMARY KEY,code TEXT NOT NULL,expires_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (username TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS leads (id TEXT PRIMARY KEY,request_key TEXT NOT NULL UNIQUE,
                    plan_id TEXT NOT NULL,ref_code TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS published_views (code TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            """)
        os.chmod(self.path, 0o600)

    @contextmanager
    def db(self, *, write: bool = False):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def resolve_agent(self, code: str) -> dict | None:
        if not re.fullmatch(r"[A-Z0-9_-]{3,24}",str(code)):
            return None
        with self.db() as db:
            row = db.execute("SELECT code,display_name,grade FROM accounts WHERE code=? AND enabled=1",(code,)).fetchone()
            return dict(row) if row else None

    def _security(self):
        if self.demo or self.maintenance or os.environ.get("ZIPING_PUBLIC_SITE") != "1":
            return None
        from public_security import controls
        return controls()

    def create_lead(self, request_key: str, plan_id: str, ref_code: str = "") -> dict:
        if plan_id not in PLAN_NAMES or not 12 <= len(request_key) <= 128:
            raise ReferralError("咨询信息不完整。")
        with self.db(write=True) as db:
            old = db.execute("SELECT * FROM leads WHERE request_key=?",(request_key,)).fetchone()
            if old:
                if old["plan_id"]!=plan_id or old["ref_code"]!=ref_code:
                    raise ReferralError("咨询请求内容不一致。")
                return dict(old)
            if gate := self._security():
                gate.rate("consultation")
            if ref_code and not db.execute("SELECT 1 FROM accounts WHERE code=? AND enabled=1",(ref_code,)).fetchone():
                raise ReferralError("推广来源暂不可用，请联系作者核对。")
            cid = identifier("ZP")
            db.execute("INSERT INTO leads VALUES(?,?,?,?,?)",(cid,request_key,plan_id,ref_code,now()))
            return dict(db.execute("SELECT * FROM leads WHERE id=?",(cid,)).fetchone())

    def _session(self, db, code: str) -> str:
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc)+timedelta(hours=8)).isoformat(timespec="seconds")
        db.execute("DELETE FROM sessions WHERE expires_at<=?",(now(),))
        db.execute("INSERT INTO sessions VALUES(?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),code,expires))
        return token

    def login(self, login: str, password: str, *, captcha_id: str = "", captcha_answer: str = "") -> str:
        gate = self._security()
        if gate:
            gate.rate("login")
        login = username(login)
        if not isinstance(password,str) or len(password)>256:
            raise ReferralError("登录名或密码不正确，或账号已暂停。")
        cutoff = (datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat(timespec="seconds")
        session = None
        with self.db(write=True) as db:
            db.execute("DELETE FROM attempts WHERE created_at<?",(cutoff,))
            failures = db.execute("SELECT COUNT(*) FROM attempts WHERE username=?",(login,)).fetchone()[0]
            if failures>=6:
                if gate:
                    gate.audit("account_login_limited")
                raise ReferralError("尝试次数较多，请 15 分钟后再试。")
            if gate and (failures>=3 or gate.captcha_required()):
                gate.verify_challenge(captcha_id,captcha_answer)
            account = db.execute("SELECT * FROM accounts WHERE username=? AND enabled=1",(login,)).fetchone()
            if account and password_matches(password,account["password_hash"]):
                db.execute("DELETE FROM attempts WHERE username=?",(login,))
                session = self._session(db,account["code"])
            else:
                db.execute("INSERT INTO attempts VALUES(?,?)",(login,now()))
        if session:
            if gate:
                gate.audit("login_succeeded")
            return session
        if gate:
            gate.failed_login()
        raise ReferralError("登录名或密码不正确，或账号已暂停。")

    def require(self, db, token: str, *, allow_password_change: bool = False) -> dict:
        row = db.execute("""SELECT a.* FROM accounts a JOIN sessions s ON s.code=a.code
                            WHERE s.digest=? AND s.expires_at>? AND a.enabled=1""",
                         (hashlib.sha256(str(token).encode()).hexdigest(),now())).fetchone()
        if not row:
            raise ReferralError("请重新登录代理账号。")
        if row["must_change_password"] and not allow_password_change:
            raise ReferralError("请先更换临时密码。")
        return dict(row)

    def identity(self, token: str) -> dict | None:
        try:
            with self.db() as db:
                row = self.require(db,token,allow_password_change=True)
                return {k:row[k] for k in ("code","username","display_name","grade","must_change_password")}
        except ReferralError:
            return None

    def logout(self, token: str):
        with self.db(write=True) as db:
            db.execute("DELETE FROM sessions WHERE digest=?",(hashlib.sha256(str(token).encode()).hexdigest(),))

    def change_password(self, token: str, old_password: str, new_password: str) -> str:
        if gate := self._security():
            gate.rate("password")
        with self.db(write=True) as db:
            user = self.require(db,token,allow_password_change=True)
            if not password_matches(old_password,user["password_hash"]):
                raise ReferralError("当前密码不正确。")
            if old_password == new_password:
                raise ReferralError("请设置与临时密码不同的新密码。")
            encoded = password_hash(new_password)
            db.execute("UPDATE accounts SET password_hash=?,must_change_password=0 WHERE code=?",(encoded,user["code"]))
            db.execute("DELETE FROM sessions WHERE code=?",(user["code"],))
            return self._session(db,user["code"])

    def demo_agents(self) -> list[dict]:
        if not self.demo:
            raise ReferralError("实际网站不提供演示身份。")
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT code,display_name FROM accounts WHERE enabled=1 ORDER BY code")]

    def demo_session(self, code: str) -> str:
        if not self.demo:
            raise ReferralError("实际账号必须使用密码登录。")
        with self.db(write=True) as db:
            if not db.execute("SELECT 1 FROM accounts WHERE code=? AND enabled=1",(code,)).fetchone():
                raise ReferralError("演示代理不存在。")
            return self._session(db,code)

    def dashboard(self, token: str) -> dict:
        with self.db() as db:
            user = self.require(db,token)
            row = db.execute("SELECT document FROM published_views WHERE code=?",(user["code"],)).fetchone()
            view = json.loads(row[0]) if row else {"orders":[],"settlements":[],"pending_cents":0,"settled_cents":0,"net_sales_cents":0}
            leads = [dict(r) for r in db.execute("SELECT id,plan_id,created_at FROM leads WHERE ref_code=? ORDER BY created_at DESC",(user["code"],))]
            meta = {r["key"]:r["value"] for r in db.execute("SELECT * FROM meta")}
            return {"agent":{k:user[k] for k in ("code","username","display_name","grade")},
                    "view":view,"leads":leads,"published_at":meta.get("published_at"),"public_url":meta.get("public_url","")}

    def public_url(self) -> str:
        with self.db() as db:
            row = db.execute("SELECT value FROM meta WHERE key='public_url'").fetchone()
            return row[0] if row else ""
