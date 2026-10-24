"""Operator-only file exchange; imported by the private tool, never a web route.

The site update is installed through a trusted deployment console/file copy.
This is not an unauthenticated upload endpoint or a digital signature scheme.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys

from referral_common import ReferralError, GRADE_RATES, PLAN_NAMES, parse_document, now
from referral_public_store import PublicStore


def _integer(value, *, minimum=0):
    if type(value) is not int or not minimum <= value <= 10**12:
        raise ReferralError("网站资料中的金额或版本不正确。")
    return value


def _timestamp(value):
    try:
        if not isinstance(value,str) or len(value)>50 or datetime.fromisoformat(value).tzinfo is None:
            raise ValueError
    except ValueError:
        raise ReferralError("网站资料中的时间不正确。") from None


def apply_publication(store: PublicStore, raw: bytes) -> int:
    data = parse_document(raw,"ziping-website-publication-v1")
    if data.get("demo") is not store.demo or not re.fullmatch(r"[a-f0-9]{32}",str(data.get("publisher_id",""))):
        raise ReferralError("发布者或演示/实际资料不匹配。")
    revision = _integer(data.get("revision"),minimum=1)
    _timestamp(data.get("published_at"))
    agents,reports = data.get("agents"),data.get("reports")
    if not isinstance(agents,list) or len(agents)>1000 or not isinstance(reports,dict):
        raise ReferralError("代理资料格式或数量不正确。")
    known,logins = set(),set()
    for row in agents:
        if not isinstance(row,dict) or set(row)!={"code","username","display_name","password_hash","credential_version","grade","enabled"}:
            raise ReferralError("发布包只允许代理登录和展示资料。")
        code = row["code"]
        if not isinstance(code,str) or not re.fullmatch(r"[A-Z0-9_-]{3,24}",code) or code in known:
            raise ReferralError("代理推广码重复或无效。")
        if not isinstance(row["username"],str) or not re.fullmatch(r"[a-z0-9_.-]{3,32}",row["username"]) or row["username"] in logins:
            raise ReferralError("代理登录名重复或无效。")
        known.add(code); logins.add(row["username"])
        if not isinstance(row["grade"],str) or row["grade"] not in GRADE_RATES or type(row["enabled"]) is not int or row["enabled"] not in (0,1):
            raise ReferralError("代理等级或状态无效。")
        if not isinstance(row["display_name"],str) or not 1<=len(row["display_name"])<=32 or not re.fullmatch(r"[a-f0-9]{32}",str(row["credential_version"])):
            raise ReferralError("代理称呼或凭据版本无效。")
        encoded = row["password_hash"]
        if not isinstance(encoded,str) or not (re.fullmatch(r"pbkdf2_sha256\$600000\$[a-f0-9]{32}\$[a-f0-9]{64}",encoded) or (store.demo and encoded=="!demo-only")):
            raise ReferralError("代理密码校验格式无效。")
    if set(reports)!=known:
        raise ReferralError("代理资料与查询视图不一致。")
    for view in reports.values():
        if not isinstance(view,dict) or set(view)!={"orders","pending_cents","settled_cents","net_sales_cents","settlements"}:
            raise ReferralError("查询视图含有不允许的字段。")
        _integer(view["pending_cents"],minimum=-10**12)
        _integer(view["settled_cents"]); _integer(view["net_sales_cents"])
        if not isinstance(view["orders"],list) or len(view["orders"])>5000 or not isinstance(view["settlements"],list) or len(view["settlements"])>5000:
            raise ReferralError("查询视图过大。")
        for order in view["orders"]:
            if not isinstance(order,dict) or set(order)!={"id","plan_id","created_at","paid","net_cents","grade","commission_cents"}:
                raise ReferralError("订单查询字段不正确。")
            if not re.fullmatch(r"ZP[A-F0-9]{12}",str(order["id"])) or not isinstance(order["plan_id"],str) or order["plan_id"] not in PLAN_NAMES or not isinstance(order["grade"],str) or order["grade"] not in GRADE_RATES or type(order["paid"]) is not bool:
                raise ReferralError("订单查询内容不正确。")
            _timestamp(order["created_at"]); _integer(order["net_cents"]); _integer(order["commission_cents"])
        for settlement in view["settlements"]:
            if not isinstance(settlement,dict) or set(settlement)!={"id","amount_cents","created_at"} or not re.fullmatch(r"JS[A-F0-9]{12}",str(settlement["id"])):
                raise ReferralError("结算查询内容不正确。")
            _integer(settlement["amount_cents"]); _timestamp(settlement["created_at"])
    url = data.get("public_url","")
    if not isinstance(url,str) or len(url)>512:
        raise ReferralError("网站地址无效。")
    with store.db(write=True) as db:
        old = {r["key"]:r["value"] for r in db.execute("SELECT * FROM meta")}
        if old.get("publisher_id") and old["publisher_id"]!=data["publisher_id"]:
            raise ReferralError("发布者与当前站点不一致，请由站点维护者核对。")
        if int(old.get("revision","0"))>=revision:
            raise ReferralError("此资料版本已经导入或较旧，请重新导出最新资料。")
        existing = {r["code"]:dict(r) for r in db.execute("SELECT * FROM accounts")}
        for row in agents:
            previous = existing.get(row["code"])
            changed = not previous or previous["credential_version"]!=row["credential_version"]
            encoded = row["password_hash"] if changed else previous["password_hash"]
            must_change = int(not store.demo) if changed else previous["must_change_password"]
            db.execute("""INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET
                          username=excluded.username,display_name=excluded.display_name,password_hash=excluded.password_hash,
                          credential_version=excluded.credential_version,grade=excluded.grade,enabled=excluded.enabled,
                          must_change_password=excluded.must_change_password""",
                       (row["code"],row["username"],row["display_name"],encoded,row["credential_version"],row["grade"],row["enabled"],must_change))
            if changed or not row["enabled"]:
                db.execute("DELETE FROM sessions WHERE code=?",(row["code"],))
        for removed in set(existing)-known:
            db.execute("UPDATE accounts SET enabled=0 WHERE code=?",(removed,))
            db.execute("DELETE FROM sessions WHERE code=?",(removed,))
        db.execute("DELETE FROM published_views")
        db.executemany("INSERT INTO published_views VALUES(?,?)",[(code,json.dumps(view,ensure_ascii=False)) for code,view in reports.items()])
        for key in ("publisher_id","revision","published_at","public_url"):
            db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(data[key])))
    return len(agents)


def export_leads(store: PublicStore) -> bytes:
    with store.db() as db:
        rows = [dict(r) for r in db.execute("SELECT id,plan_id,ref_code,created_at FROM leads ORDER BY created_at")]
    return json.dumps({"format":"ziping-public-leads-v1","demo":store.demo,"exported_at":now(),"leads":rows},ensure_ascii=False).encode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="站点维护者在部署终端交换资料；没有公网管理接口")
    parser.add_argument("command",choices=["apply","export-leads"])
    parser.add_argument("file",type=Path)
    parser.add_argument("--demo",action="store_true")
    parser.add_argument("--data-root",type=Path)
    args = parser.parse_args()
    try:
        store = PublicStore(demo=args.demo,root=args.data_root,maintenance=True)
        if args.command=="apply":
            print("已更新代理数量：",apply_publication(store,args.file.read_bytes()))
        else:
            args.file.parent.mkdir(parents=True,exist_ok=True)
            args.file.write_bytes(export_leads(store))
            print("咨询线索已导出。")
    except (ReferralError,OSError) as error:
        parser.exit(1,str(error)+"\n")
