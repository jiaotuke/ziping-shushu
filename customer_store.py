"""Separate customer accounts and private saved birth inputs; no model credentials."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from runtime_paths import DATA_ROOT


class CustomerError(ValueError):
    pass

VIP_SCHEMA = """CREATE TABLE IF NOT EXISTS vip_entitlements (user_id TEXT PRIMARY KEY REFERENCES customers(id), enabled INTEGER NOT NULL DEFAULT 0, expires REAL, revision INTEGER NOT NULL DEFAULT 0)"""

MAX_FAVORITE_REPORTS = 30
MAX_FAVORITE_BYTES = 5 * 1024 * 1024
MAX_FAVORITE_TOTAL = 20 * 1024 * 1024


def _username(value: str) -> str:
    value = str(value).strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", value):
        raise CustomerError("用户名请使用3至32位英文字母、数字、点、横线或下划线。")
    return value


def _password(value: str):
    if not isinstance(value, str) or not 10 <= len(value) <= 128:
        raise CustomerError("密码长度需为10至128位。")


def _hash(value: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", value.encode(), salt.encode(), 600000).hex()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# Strict allowlists keep model keys, reports, session state and account tokens out.
FORM_KEYS = frozenset(("calendar_type", "gender", "birth_date", "lunar_year", "lunar_month", "lunar_day",
                      "is_leap_month", "birth_time", "use_true_solar_time", "location", "fold_choice", "pillars", "professional_birth"))
INPUT_KEYS = frozenset(("calendar_type", "birth_gender", "birth_time", "birth_province", "solar_birth_year",
                       "solar_birth_month", "solar_birth_day", "lunar_birth_year", "lunar_birth_month", "lunar_birth_day",
                       "portable_load_location", "use_true_solar_time", "fold_choice", "manual_matched_birth"))
REGION_KEYS = frozenset(("name", "adcode", "center", "childrenNum", "children_num", "path", "coordinate_level", "longitude", "latitude", "timezone", "省", "市", "区", "经度", "纬度", "时区"))


def birth_input_key(key: str) -> bool:
    return key in INPUT_KEYS or bool(re.fullmatch(r"manual_select_(?:年柱|月柱|日柱|时柱)|birth_(?:city|county)_[0-9]{6}", key))


def validate_payload(payload: dict) -> str:
    if not isinstance(payload, dict) or set(payload) != {"version", "form", "inputs"} or payload["version"] != 1:
        raise CustomerError("排盘存档格式不正确，请重新排盘后保存。")
    form, inputs = payload["form"], payload["inputs"]
    if not isinstance(form, dict) or set(form)-FORM_KEYS or not isinstance(inputs, dict) or any(not birth_input_key(k) for k in inputs):
        raise CustomerError("排盘存档包含不支持的字段。")
    if form.get("calendar_type") not in ("公历", "农历", "四柱八字") or form.get("gender") not in ("男", "女"):
        raise CustomerError("请先完成有效排盘再保存。")
    # Nested keys are also restricted; no arbitrary dictionaries or hidden text.
    for key, value in form.items():
        if isinstance(value, dict):
            allowed = {"年柱", "月柱", "日柱", "时柱"} if key == "pillars" else REGION_KEYS if key == "location" else set()
            if set(value)-allowed:
                raise CustomerError("出生资料含有不支持的字段。")
    for value in inputs.values():
        if isinstance(value, dict) and set(value)-REGION_KEYS:
            raise CustomerError("地点资料含有不支持的字段。")
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode()) > 24000:
        raise CustomerError("排盘资料过大，无法保存。")
    return encoded


class CustomerStore:
    def __init__(self):
        root = DATA_ROOT / "customers"
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        self.path = root / "accounts.sqlite3"
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL, recovery_hash TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES customers(id), expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS failures (username TEXT NOT NULL, at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS failures_user ON failures(username,at);
                CREATE TABLE IF NOT EXISTS charts (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES customers(id),
                    fingerprint TEXT NOT NULL, title TEXT NOT NULL, note TEXT NOT NULL,
                    summary TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                    UNIQUE(user_id,fingerprint));
                CREATE INDEX IF NOT EXISTS charts_owner ON charts(user_id,updated);
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES customers(id),
                    chart_id TEXT REFERENCES charts(id) ON DELETE SET NULL,
                    fingerprint TEXT NOT NULL, title TEXT NOT NULL, note TEXT NOT NULL,
                    filename TEXT NOT NULL, html BLOB, txt BLOB, json BLOB,
                    size_bytes INTEGER NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                    UNIQUE(user_id,fingerprint));
                CREATE INDEX IF NOT EXISTS reports_owner ON reports(user_id,updated);
            """)
        with self.db() as db:
            db.execute(VIP_SCHEMA)
            db.execute("""CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES customers(id),title TEXT NOT NULL,snapshot TEXT NOT NULL,messages TEXT NOT NULL,updated REAL NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(user_id,updated)")
        os.chmod(self.path, 0o600)

    @contextmanager
    def db(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _user(self, db, token):
        user = db.execute("""SELECT c.id,c.username FROM customers c JOIN sessions s ON s.user_id=c.id
                           WHERE s.digest=? AND s.expires>?""", (_digest(str(token)), time.time())).fetchone()
        if not user:
            raise CustomerError("请先登录，或在登录过期后重新登录。")
        return dict(user)

    def identity(self, token):
        with self.db() as db:
            try:
                return self._user(db, token)
            except CustomerError:
                return None

    def _session(self, db, uid):
        db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES(?,?,?)", (_digest(token), uid, time.time()+8*3600))
        return token

    def register(self, username, password):
        username = _username(username)
        _password(password)
        salt, recovery = secrets.token_hex(16), secrets.token_urlsafe(24)
        with self.db(write=True) as db:
            if db.execute("SELECT 1 FROM customers WHERE username=?", (username,)).fetchone():
                raise CustomerError("该用户名暂不可用，请换一个。")
            uid = secrets.token_hex(16)
            db.execute("INSERT INTO customers VALUES(?,?,?,?,?,?)", (uid,username,salt,_hash(password,salt),_hash(recovery,salt),time.time()))
            return self._session(db, uid), recovery

    def login(self, username, password):
        username = _username(username)
        if not isinstance(password,str) or len(password)>128:
            raise CustomerError("用户名或密码不正确。")
        failed = False
        with self.db(write=True) as db:
            db.execute("DELETE FROM failures WHERE at<?", (time.time()-900,))
            if db.execute("SELECT COUNT(*) FROM failures WHERE username=?", (username,)).fetchone()[0] >= 6:
                raise CustomerError("该账号尝试过于频繁，请15分钟后再试。")
            row = db.execute("SELECT * FROM customers WHERE username=?", (username,)).fetchone()
            actual = _hash(password, row["salt"] if row else "0"*32)
            if not row or not hmac.compare_digest(actual, row["password_hash"]):
                db.execute("INSERT INTO failures VALUES(?,?)", (username,time.time()))
                failed = True
            else:
                db.execute("DELETE FROM failures WHERE username=?", (username,))
                token = self._session(db, row["id"])
        if failed:
            raise CustomerError("用户名或密码不正确。")
        return token

    def logout(self, token):
        with self.db(write=True) as db:
            db.execute("DELETE FROM sessions WHERE digest=?", (_digest(str(token)),))

    def recover(self, username, recovery, password):
        username = _username(username)
        _password(password)
        if not isinstance(recovery,str) or not 20<=len(recovery)<=128:
            raise CustomerError("用户名或恢复码不正确。")
        failed = False
        with self.db(write=True) as db:
            db.execute("DELETE FROM failures WHERE at<?", (time.time()-900,))
            if db.execute("SELECT COUNT(*) FROM failures WHERE username=?", (username,)).fetchone()[0]>=6:
                raise CustomerError("该账号尝试过于频繁，请15分钟后再试。")
            row = db.execute("SELECT * FROM customers WHERE username=?", (username,)).fetchone()
            actual = _hash(recovery, row["salt"] if row else "0"*32)
            if not row or not hmac.compare_digest(actual, row["recovery_hash"]):
                db.execute("INSERT INTO failures VALUES(?,?)", (username,time.time()))
                failed = True
            else:
                salt, next_code = secrets.token_hex(16), secrets.token_urlsafe(24)
                db.execute("UPDATE customers SET salt=?,password_hash=?,recovery_hash=? WHERE id=?",
                           (salt,_hash(password,salt),_hash(next_code,salt),row["id"]))
                db.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
                db.execute("DELETE FROM failures WHERE username=?", (username,))
        if failed:
            raise CustomerError("用户名或恢复码不正确。")
        return next_code

    def save(self, token, title, note, summary, payload):
        title, note = str(title).strip(), str(note).strip()
        if not 1<=len(title)<=40 or len(note)>300:
            raise CustomerError("名称需为1至40字，备注最多300字。")
        encoded = validate_payload(payload)
        fingerprint = _digest(json.dumps(payload["form"],ensure_ascii=False,sort_keys=True))
        with self.db(write=True) as db:
            uid = self._user(db,token)["id"]
            existing = db.execute("SELECT id FROM charts WHERE user_id=? AND fingerprint=?", (uid,fingerprint)).fetchone()
            if existing:
                cid = existing["id"]
                db.execute("UPDATE charts SET title=?,note=?,summary=?,payload=?,updated=? WHERE id=? AND user_id=?",
                           (title,note,str(summary)[:500],encoded,time.time(),cid,uid))
            else:
                if db.execute("SELECT COUNT(*) FROM charts WHERE user_id=?", (uid,)).fetchone()[0]>=100:
                    raise CustomerError("每个账号最多保存100份排盘，请先删除不需要的记录。")
                cid = secrets.token_hex(16)
                now=time.time()
                db.execute("INSERT INTO charts VALUES(?,?,?,?,?,?,?,?,?)", (cid,uid,fingerprint,title,note,str(summary)[:500],encoded,now,now))
            return cid

    def list_charts(self, token):
        with self.db() as db:
            uid=self._user(db,token)["id"]
            return [dict(r) for r in db.execute("SELECT id,title,note,summary,updated FROM charts WHERE user_id=? ORDER BY updated DESC",(uid,))]

    def load(self, token, cid):
        with self.db() as db:
            uid=self._user(db,token)["id"]
            row=db.execute("SELECT payload FROM charts WHERE id=? AND user_id=?",(cid,uid)).fetchone()
            if not row:
                raise CustomerError("排盘不存在或不属于当前账号。")
            payload=json.loads(row["payload"])
            validate_payload(payload)
            return payload

    def delete(self, token, cid):
        with self.db(write=True) as db:
            uid=self._user(db,token)["id"]
            if db.execute("DELETE FROM charts WHERE id=? AND user_id=?",(cid,uid)).rowcount!=1:
                raise CustomerError("排盘不存在或已删除。")


    def report_usage(self, token):
        with self.db() as db:
            uid = self._user(db,token)["id"]
            row = db.execute("SELECT COUNT(*),COALESCE(SUM(size_bytes),0) FROM reports WHERE user_id=?",(uid,)).fetchone()
            return {"count":row[0], "bytes":row[1]}

    def save_report(self, token, title, note, chart_id, filename, files):
        title, note = str(title).strip(), str(note).strip()
        if not 1<=len(title)<=80 or len(note)>300:
            raise CustomerError("报告名称需为1至80字，备注最多300字。")
        if not isinstance(files,dict) or not files or set(files)-{"html","txt","json"}:
            raise CustomerError("仅支持HTML、TXT和本程序生成的JSON报告。")
        if any(not isinstance(value,bytes) or not value for value in files.values()):
            raise CustomerError("报告为空或内容格式不正确。")
        size = sum(len(value) for value in files.values())
        if size > MAX_FAVORITE_BYTES:
            raise CustomerError("单份收藏最多5MB（含其下载格式）。")
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(filename))[:140].strip(" .") or "子平术数报告"
        digest=hashlib.sha256()
        for ext, raw in sorted(files.items()):
            digest.update(ext.encode()+b"\0"+len(raw).to_bytes(8,"big")+raw)
        # Generated exports embed a fresh export timestamp on every rerender.
        # Ignore only that timestamp so collecting the same report is idempotent.
        if "json" in files:
            try:
                artifact = json.loads(files["json"].decode("utf-8-sig"))
                if isinstance(artifact, dict) and artifact.get("format") in ("ziping-report-v4-importable", "ziping-period-report-v1"):
                    artifact.pop("exported_at", None)
                    digest = hashlib.sha256(json.dumps(artifact,ensure_ascii=False,sort_keys=True,allow_nan=False).encode())
            except (ValueError, UnicodeError, RecursionError):
                raise CustomerError("报告数据格式不正确，请重新下载后收藏。") from None
        fingerprint=digest.hexdigest()
        with self.db(write=True) as db:
            uid=self._user(db,token)["id"]
            if chart_id and not db.execute("SELECT 1 FROM charts WHERE id=? AND user_id=?",(chart_id,uid)).fetchone():
                raise CustomerError("关联排盘不存在或不属于当前账号。")
            existing=db.execute("SELECT id,size_bytes FROM reports WHERE user_id=? AND fingerprint=?",(uid,fingerprint)).fetchone()
            usage=db.execute("SELECT COUNT(*),COALESCE(SUM(size_bytes),0) FROM reports WHERE user_id=?",(uid,)).fetchone()
            if not existing and usage[0]>=MAX_FAVORITE_REPORTS:
                raise CustomerError("每个账号最多收藏30份报告，请先删除不需要的收藏。")
            if usage[1]-(existing["size_bytes"] if existing else 0)+size>MAX_FAVORITE_TOTAL:
                raise CustomerError("报告收藏总空间最多20MB，请先删除不需要的收藏。")
            if existing:
                rid=existing["id"]
                db.execute("UPDATE reports SET title=?,note=?,chart_id=?,filename=?,updated=? WHERE id=? AND user_id=?",
                           (title,note,chart_id or None,filename,time.time(),rid,uid))
            else:
                rid=secrets.token_hex(16)
                now=time.time()
                db.execute("INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (rid,uid,chart_id or None,fingerprint,title,note,filename,files.get("html"),files.get("txt"),files.get("json"),size,now,now))
            return rid

    def list_reports(self, token):
        with self.db() as db:
            uid=self._user(db,token)["id"]
            return [dict(row) for row in db.execute("""SELECT r.id,r.title,r.note,r.filename,r.size_bytes,r.updated,r.chart_id,c.title AS chart_title
                FROM reports r LEFT JOIN charts c ON c.id=r.chart_id AND c.user_id=r.user_id
                WHERE r.user_id=? ORDER BY r.updated DESC""",(uid,))]

    def load_report(self, token, rid):
        with self.db() as db:
            uid=self._user(db,token)["id"]
            row=db.execute("SELECT * FROM reports WHERE id=? AND user_id=?",(rid,uid)).fetchone()
            if not row:
                raise CustomerError("报告不存在或不属于当前账号。")
            return dict(row)

    def delete_report(self, token, rid):
        with self.db(write=True) as db:
            uid=self._user(db,token)["id"]
            if db.execute("DELETE FROM reports WHERE id=? AND user_id=?",(rid,uid)).rowcount!=1:
                raise CustomerError("报告不存在或已删除。")


    def vip_status(self, token):
        with self.db() as db:
            user=self._user(db,token)
            row=db.execute("SELECT enabled,expires,revision FROM vip_entitlements WHERE user_id=?",(user["id"],)).fetchone()
            active=bool(row and row["enabled"] and (row["expires"] is None or row["expires"]>time.time()))
            return {"active":active,"expires":row["expires"] if row else None,"revision":row["revision"] if row else 0}

    def require_vip(self, token):
        if not self.vip_status(token)["active"]:
            raise CustomerError("此功能需VIP资格，请联系作者人工开通；模型调用仍使用你自己的API Key。")

    def list_conversations(self, token):
        with self.db() as db:
            uid=self._user(db,token)["id"]
            return [dict(row) for row in db.execute("SELECT id,title,updated FROM conversations WHERE user_id=? ORDER BY updated DESC",(uid,))]

    def load_conversation(self, token, cid):
        with self.db() as db:
            uid=self._user(db,token)["id"]
            row=db.execute("SELECT * FROM conversations WHERE id=? AND user_id=?",(cid,uid)).fetchone()
            if not row:raise CustomerError("对话不存在或不属于当前账号。")
            value=dict(row)
            value["snapshot"]=json.loads(value["snapshot"])
            value["messages"]=json.loads(value["messages"])
            return value

    def save_conversation(self, token, cid, title, snapshot, messages):
        from report_chat import validate_snapshot, validate_history
        validate_snapshot(snapshot)
        validate_history(messages,snapshot)
        title=str(title).strip()
        if not 1<=len(title)<=80:raise CustomerError("对话名称需为1至80字。")
        raw=json.dumps(snapshot,ensure_ascii=False,allow_nan=False)
        history=json.dumps(messages,ensure_ascii=False,allow_nan=False)
        if len(raw.encode())+len(history.encode())>8*1024*1024:raise CustomerError("这段对话及绑定报告超过8MB，未保存，请检查报告大小。")
        with self.db(write=True) as db:
            uid=self._user(db,token)["id"]
            existing=db.execute("SELECT id,snapshot FROM conversations WHERE id=? AND user_id=?",(cid,uid)).fetchone() if cid else None
            if cid and not existing:raise CustomerError("对话不存在或已被删除，请另存新对话。")
            if existing and json.loads(existing['snapshot'])['fingerprint']!=snapshot['fingerprint']:
                raise CustomerError("对话绑定的报告版本不能更换，请新建对话。")
            if not existing:
                row=db.execute("SELECT enabled,expires FROM vip_entitlements WHERE user_id=?",(uid,)).fetchone()
                if not row or not row["enabled"] or row["expires"] is not None and row["expires"]<=time.time():
                    raise CustomerError("新建并保存对话需要有效VIP资格。")
                if db.execute("SELECT COUNT(*) FROM conversations WHERE user_id=?",(uid,)).fetchone()[0]>=20:
                    raise CustomerError("每个账号最多保存20段对话，请先删除不需要的记录。")
            others=db.execute("SELECT COALESCE(SUM(length(CAST(snapshot AS BLOB))+length(CAST(messages AS BLOB))),0) FROM conversations WHERE user_id=? AND id<>?",(uid,cid or '')).fetchone()[0]
            if others+len(raw.encode())+len(history.encode())>10*1024*1024:raise CustomerError("对话保存总空间最多10MB。")
            if existing:
                db.execute("UPDATE conversations SET title=?,messages=?,updated=? WHERE id=? AND user_id=?",(title,history,time.time(),cid,uid))
            else:
                cid=secrets.token_hex(16)
                db.execute("INSERT INTO conversations VALUES(?,?,?,?,?,?)",(cid,uid,title,raw,history,time.time()))
            return cid

    def delete_conversation(self, token, cid):
        with self.db(write=True) as db:
            uid=self._user(db,token)["id"]
            if db.execute("DELETE FROM conversations WHERE id=? AND user_id=?",(cid,uid)).rowcount!=1:
                raise CustomerError("对话不存在或已删除。")
