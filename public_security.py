"""Public-site abuse controls shared across sessions; no model keys or request bodies logged."""
from __future__ import annotations
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import hmac
import io
import ipaddress
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from referral_common import ReferralError
from runtime_paths import DATA_ROOT


class PublicSecurityError(ReferralError):
    pass


class CaptchaRequired(PublicSecurityError):
    pass


POLICIES = {
    'chat': ((6, 60), (100, 3600), (40, 60, 'global')),
    'customer_register': ((3, 3600), (6, 86400), (100, 3600, 'global'), (500, 86400, 'global')),
    'customer_save': ((15, 60), (200, 3600), (120, 60, 'global')),
    'login': ((15, 60), (60, 900), (120, 60, 'global')),
    'captcha': ((12, 60), (40, 900), (120, 60, 'global')),
    'consultation': ((3, 60), (20, 86400), (30, 60, 'global'), (500, 86400, 'global')),
    'chart': ((20, 60), (200, 3600), (120, 60, 'global')),
    'search': ((10, 60), (100, 3600), (90, 60, 'global')),
    'report': ((3, 600), (12, 86400), (20, 3600, 'global')),
    'translation': ((3, 600), (12, 86400), (20, 3600, 'global')),
    'connection': ((6, 300), (30, 3600, 'global')),
    'password': ((5, 60), (15, 900), (60, 900, 'global')),
}
_INITIALIZE_LOCK = threading.Lock()


def enabled() -> bool:
    return os.environ.get('ZIPING_PUBLIC_SITE') == '1'


def client_address() -> str:
    import streamlit as st
    # Only the Docker public service enables this flag. Caddy always overwrites
    # the header from its actual remote peer; port 8501 remains loopback-only.
    candidate = None
    if os.environ.get('ZIPING_TRUST_PROXY_HEADER') == '1':
        candidate = st.context.headers.get('X-Ziping-Client-IP')
    if not candidate:
        candidate = st.context.ip_address
    try:
        return ipaddress.ip_address(str(candidate)).compressed
    except ValueError:
        return 'unknown-source'  # Shared fail-closed bucket, never a random bypass identity.


class _Controls:
    def __init__(self):
        self.root = DATA_ROOT / 'security'
        self.root.mkdir(parents=True, exist_ok=True)
        key_file = self.root / 'source-key.private'
        try:
            with key_file.open('xb') as target:
                os.chmod(key_file, 0o600)
                target.write(secrets.token_bytes(32))
        except FileExistsError:
            pass
        self.key = key_file.read_bytes()
        for _ in range(20):
            if len(self.key) == 32:
                break
            time.sleep(0.01)
            self.key = key_file.read_bytes()
        if len(self.key) != 32:
            raise PublicSecurityError('安全控制暂不可用，请稍后重试。')
        self.path = self.root / 'controls.sqlite3'
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS events(action TEXT NOT NULL,subject TEXT NOT NULL,at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS event_subject ON events(action,subject,at);
            CREATE INDEX IF NOT EXISTS event_global ON events(action,at);
            CREATE INDEX IF NOT EXISTS event_age ON events(at);
            CREATE TABLE IF NOT EXISTS audit(minute INTEGER NOT NULL,event TEXT NOT NULL,count INTEGER NOT NULL,
                PRIMARY KEY(minute,event));
            CREATE TABLE IF NOT EXISTS leases(id TEXT PRIMARY KEY,subject TEXT NOT NULL,purpose TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS challenges(id TEXT PRIMARY KEY,subject TEXT NOT NULL,answer TEXT NOT NULL,expires REAL NOT NULL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=4)
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except sqlite3.Error:
            db.rollback()
            raise PublicSecurityError('安全控制暂时繁忙，请稍后重试。') from None
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def subject(self) -> str:
        return hmac.new(self.key, client_address().encode(), hashlib.sha256).hexdigest()

    def audit(self, event: str):
        # Event labels are internal constants only. Aggregate by minute; never
        # store IPs, names, birth data, API keys, passwords, or session tokens.
        try:
            with self.db() as db:
                minute = int(time.time()) // 60 * 60
                db.execute('DELETE FROM audit WHERE minute<?', (minute - 7 * 86400,))
                db.execute('INSERT INTO audit VALUES(?,?,1) ON CONFLICT(minute,event) DO UPDATE SET count=count+1', (minute, event))
        except PublicSecurityError:
            pass  # An optional audit write must not hide a successful transaction.

    def rate(self, action: str):
        now, subject = time.time(), self.subject()
        blocked = False
        with self.db() as db:
            db.execute('DELETE FROM events WHERE at<?', (now - 86400,))
            for rule in POLICIES[action]:
                limit, window = rule[:2]
                if len(rule) == 3:
                    count = db.execute('SELECT COUNT(*) FROM events WHERE action=? AND at>?', (action, now-window)).fetchone()[0]
                else:
                    count = db.execute('SELECT COUNT(*) FROM events WHERE action=? AND subject=? AND at>?', (action, subject, now-window)).fetchone()[0]
                if count >= limit:
                    blocked = True
                    break
            if not blocked:
                db.execute('INSERT INTO events VALUES(?,?,?)', (action, subject, now))
        if blocked:
            self.audit(action + '_limited')
            raise PublicSecurityError('操作过于频繁，请稍后重试。')

    def failed_login(self):
        with self.db() as db:
            db.execute('INSERT INTO events VALUES(?,?,?)', ('login_failure', self.subject(), time.time()))
        self.audit('login_failed')

    def captcha_required(self) -> bool:
        with self.db() as db:
            return db.execute('SELECT COUNT(*) FROM events WHERE action=? AND subject=? AND at>?',
                              ('login_failure', self.subject(), time.time()-900)).fetchone()[0] >= 3

    def challenge(self) -> tuple[str, bytes]:
        from PIL import Image, ImageDraw, ImageFont
        self.rate('captcha')
        answer = ''.join(secrets.choice('23456789ABCDEFGHJKLMNPQRSTUVWXYZ') for _ in range(5))
        identifier = secrets.token_urlsafe(24)
        digest = hmac.new(self.key, (identifier + ':' + answer).encode(), hashlib.sha256).hexdigest()
        with self.db() as db:
            db.execute('DELETE FROM challenges WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO challenges VALUES(?,?,?,?)', (identifier, self.subject(), digest, time.time()+180))
        canvas = Image.new('RGB', (190, 60), '#202329')
        draw = ImageDraw.Draw(canvas)
        for _ in range(70):
            x,y=secrets.randbelow(190),secrets.randbelow(60)
            draw.point((x,y),fill='#71808d')
        try:
            font=ImageFont.load_default(size=30)
        except TypeError:
            font=ImageFont.load_default()
        for index,char in enumerate(answer):
            glyph=Image.new('RGBA',(36,48))
            ImageDraw.Draw(glyph).text((6,4),char,font=font,fill='#e7c27c')
            glyph=glyph.rotate(secrets.randbelow(25)-12,resample=Image.Resampling.BICUBIC)
            canvas.paste(glyph,(5+index*36,5+secrets.randbelow(5)),glyph)
        output=io.BytesIO()
        canvas.save(output,format='PNG')
        return identifier,output.getvalue()

    def verify_challenge(self, identifier: str, answer: str):
        if not isinstance(identifier,str) or len(identifier)>80 or not isinstance(answer,str) or len(answer)>16:
            raise CaptchaRequired('请完成验证码后登录。')
        with self.db() as db:
            row=db.execute('SELECT subject,answer,expires FROM challenges WHERE id=?',(identifier,)).fetchone()
            db.execute('DELETE FROM challenges WHERE id=?',(identifier,))
        actual=hmac.new(self.key,(identifier+':'+answer.strip().upper()).encode(),hashlib.sha256).hexdigest()
        if not row or row[0]!=self.subject() or row[2]<time.time() or not hmac.compare_digest(row[1],actual):
            self.audit('captcha_failed')
            raise CaptchaRequired('验证码不正确或已过期，请换一张后重试。')

    def acquire(self, purpose: str):
        subject, now, identifier=self.subject(),time.time(),secrets.token_urlsafe(24)
        blocked=False
        with self.db() as db:
            db.execute('DELETE FROM leases WHERE expires<?',(now,))
            maximum=max(1,min(4,int(os.environ.get('ZIPING_MAX_AI_TASKS','2'))))
            total=db.execute('SELECT COUNT(*) FROM leases').fetchone()[0]
            own=db.execute('SELECT COUNT(*) FROM leases WHERE subject=?',(subject,)).fetchone()[0]
            if total>=maximum or own>=1:
                blocked=True
            else:
                db.execute('INSERT INTO leases VALUES(?,?,?,?)',(identifier,subject,purpose,now+300))
        if blocked:
            self.audit('task_capacity_reached')
            raise PublicSecurityError('当前生成任务较多，或你已有任务正在生成，请稍后重试。')
        return identifier


@lru_cache(maxsize=1)
def controls() -> _Controls:
    with _INITIALIZE_LOCK:
        return _Controls()


def check_action(action: str):
    if enabled():
        controls().rate(action)


def login_needs_challenge() -> bool:
    return enabled() and controls().captcha_required()


def permit_ui_action(action: str) -> bool:
    try:
        check_action(action)
        return True
    except PublicSecurityError as error:
        import streamlit as st
        st.session_state['_public_security_notice'] = str(error)
        return False


@contextmanager
def generation_slot(purpose: str, *, rate_action: bool = True):
    if not enabled():
        yield
        return
    gate=controls()
    identifier=gate.acquire(purpose)
    try:
        if rate_action:
            gate.rate(purpose)
    except BaseException:
        with gate.db() as db:
            db.execute('DELETE FROM leases WHERE id=?',(identifier,))
        raise
    stopped=threading.Event()
    def heartbeat():
        while not stopped.wait(30):
            try:
                with gate.db() as db:
                    db.execute('UPDATE leases SET expires=? WHERE id=?',(time.time()+300,identifier))
            except (sqlite3.Error, PublicSecurityError):
                pass  # The bounded lease expires if the process cannot renew it.
    worker=threading.Thread(target=heartbeat,name='ziping-task-lease',daemon=True)
    worker.start()
    gate.audit('task_started')
    try:
        yield
    finally:
        stopped.set()
        try:
            with gate.db() as db:
                db.execute('DELETE FROM leases WHERE id=?',(identifier,))
        except PublicSecurityError:
            pass  # A stale lease expires conservatively if storage is busy.
        gate.audit('task_finished')


def security_status() -> dict:
    gate=controls()
    with gate.db() as db:
        running=db.execute('SELECT COUNT(*) FROM leases WHERE expires>?',(time.time(),)).fetchone()[0]
        events={name:count for name,count in db.execute('SELECT event,SUM(count) FROM audit WHERE minute>? GROUP BY event',(time.time()-900,))}
    host_file=gate.root/'host-status.json'
    try:
        host=json.loads(host_file.read_text(encoding='utf-8'))
    except (OSError,ValueError):
        host={}
    return {'running_ai_tasks':running,'max_ai_tasks':int(os.environ.get('ZIPING_MAX_AI_TASKS','2')),
            'last_15_minutes':events,'host':host}
