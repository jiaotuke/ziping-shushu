"""First-party aggregate page statistics; no raw addresses, URLs, or credentials stored."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import hmac
import ipaddress
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from zoneinfo import ZoneInfo

from runtime_paths import DATA_ROOT

ROOT = DATA_ROOT / 'analytics'
ZONE = ZoneInfo('Asia/Shanghai')
_LOCK = threading.Lock()
_BOTS = ('bot', 'spider', 'crawler', 'headless', 'python', 'curl/', 'wget/',
         'uptime', 'monitor', 'lighthouse', 'healthcheck', 'go-http-client')


@contextmanager
def _database(path, *, write=False):
    connection = sqlite3.connect(str(path) if write else path.resolve().as_uri()+'?mode=ro',
                                 uri=not write, timeout=.5)
    try:
        connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield connection
        if write:
            connection.commit()
    except BaseException:
        if write:
            connection.rollback()
        raise
    finally:
        connection.close()


@lru_cache(maxsize=1)
def initialize():
    with _LOCK:
        ROOT.mkdir(parents=True, exist_ok=True)
        os.chmod(ROOT, 0o700)
        path = ROOT / 'visits.sqlite3'
        key_path = ROOT / 'visitor-key.private'
        try:
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, 'wb') as target:
                target.write(secrets.token_bytes(32))
        key = key_path.read_bytes()
        for _ in range(20):
            if len(key) == 32:
                break
            time.sleep(.01)
            key = key_path.read_bytes()
        if len(key) != 32:
            raise OSError('Analytics key is not ready')
        with _database(path, write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS daily (day TEXT PRIMARY KEY,views INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS visitors (day TEXT NOT NULL,fingerprint TEXT NOT NULL,PRIMARY KEY(day,fingerprint))')
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)',
                       ('started_at', datetime.now(timezone.utc).isoformat(timespec='seconds')))
        os.chmod(path, 0o600)
    return path, key


def record_page(page='chart'):
    """One view per page entry, not per Streamlit widget rerun or generation stage."""
    if os.environ.get('ZIPING_PUBLIC_SITE') != '1':
        return
    import streamlit as st
    from public_security import client_address
    page = page if page in ('chart', 'agent') else 'chart'
    if st.session_state.get('_analytics_last_page') == page:
        return
    agent = str(st.context.headers.get('User-Agent') or '')[:256]
    if not agent or any(label in agent.lower() for label in _BOTS):
        st.session_state['_analytics_last_page'] = page
        return
    try:
        path, key = initialize()
        today = datetime.now(ZONE).date()
        address = client_address()
        try:
            address = ipaddress.ip_address(address).compressed
        except ValueError:
            address = None
        # Only the keyed digest is persisted, never the IP, browser string, or query.
        fingerprint = hmac.new(key, (address+'\n'+agent).encode(), hashlib.sha256).hexdigest() if address else None
        with _database(path, write=True) as db:
            db.execute('INSERT INTO daily VALUES(?,1) ON CONFLICT(day) DO UPDATE SET views=views+1',
                       (today.isoformat(),))
            if fingerprint:
                db.execute('INSERT OR IGNORE INTO visitors VALUES(?,?)', (today.isoformat(),fingerprint))
            if db.execute("SELECT value FROM meta WHERE key='last_cleanup'").fetchone() != (today.isoformat(),):
                db.execute('DELETE FROM visitors WHERE day<?', ((today-timedelta(days=34)).isoformat(),))
                db.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                           ('last_cleanup', today.isoformat()))
        st.session_state['_analytics_last_page'] = page
    except (OSError, sqlite3.Error):
        pass  # Optional measurement must never prevent access or erase a report.


def snapshot():
    """Aggregate-only snapshot for a trusted maintenance connection; no public endpoint."""
    now = datetime.now(ZONE)
    today = now.date()
    cutoff = (today-timedelta(days=29)).isoformat()
    days = [(today-timedelta(days=offset)).isoformat() for offset in range(29,-1,-1)]
    path = ROOT/'visits.sqlite3'
    enabled = path.is_file()
    totals, by_day, visitors, started = 0, {}, {}, None
    unique_7 = unique_30 = 0
    if enabled:
        with _database(path) as db:
            started_row = db.execute("SELECT value FROM meta WHERE key='started_at'").fetchone()
            started = started_row[0] if started_row else None
            totals = db.execute('SELECT COALESCE(SUM(views),0) FROM daily').fetchone()[0]
            by_day = dict(db.execute('SELECT day,views FROM daily WHERE day>=? AND day<=?',(cutoff,days[-1])))
            visitors = dict(db.execute('SELECT day,COUNT(*) FROM visitors WHERE day>=? AND day<=? GROUP BY day',(cutoff,days[-1])))
            unique_7 = db.execute('SELECT COUNT(DISTINCT fingerprint) FROM visitors WHERE day>=? AND day<=?',(days[-7],days[-1])).fetchone()[0]
            unique_30 = db.execute('SELECT COUNT(DISTINCT fingerprint) FROM visitors WHERE day>=? AND day<=?',(cutoff,days[-1])).fetchone()[0]
    daily = [{'date':day,'views':by_day.get(day,0),'visitors':visitors.get(day,0)} for day in days]
    return {'format':'ziping-traffic-v1','enabled':enabled,'timezone':'Asia/Shanghai',
            'started_at':started,'updated_at':now.isoformat(timespec='seconds'),
            'summary':{'today_views':by_day.get(days[-1],0),'today_visitors':visitors.get(days[-1],0),
                       'last_7_views':sum(by_day.get(day,0) for day in days[-7:]),
                       'last_30_views':sum(by_day.values()),'total_views':totals,
                       'last_7_visitors':unique_7,'last_30_visitors':unique_30},'daily':daily}
