"""Customer and agent pages only. No administrator module or ledger import."""
from __future__ import annotations
import csv
from datetime import datetime
import io
import os
import re
import secrets
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import streamlit as st
from referral_common import PLAN_NAMES, WECHAT_ID, GRADE_RATES, ReferralError
from referral_public_store import PublicStore

@st.cache_resource(show_spinner=False)
def _store(demo: bool) -> PublicStore:
    return PublicStore(demo=demo)

def _demo() -> bool:
    return os.environ.get("ZIPING_ALLOW_REFERRAL_DEMO") == "1" and st.query_params.get("demo") == "1"


def _mode() -> str:
    return "demo" if _demo() else "live"



def _yuan(cents: int) -> str:
    return f"¥{cents / 100:,.2f}"



def _time(value: str | None) -> str:
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%m-%d %H:%M") if value else "—"



_CHART_INPUT_KEYS = frozenset({
    "calendar_type", "birth_gender", "birth_time", "birth_province",
    "solar_birth_year", "solar_birth_month", "solar_birth_day",
    "lunar_birth_year", "lunar_birth_month", "lunar_birth_day",
    "is_leap_month", "portable_load_location", "use_true_solar_time", "fold_choice",
    "manual_matched_birth", "ai_service_mode", "ai_provider", "ai_thinking",
    "ai_analysis_scope", "glm_api_key", "deepseek_api_key",
})
_CHART_INPUT_PREFIXES = (
    "manual_select_", "birth_city_", "birth_county_", "paid_pick_",
    "ai_model_", "ai_custom_", "ai_window_",
)


def _is_chart_input(name: str) -> bool:
    """Only replay editable inputs, never buttons, components, or job state."""
    return (name in _CHART_INPUT_KEYS or name.startswith(_CHART_INPUT_PREFIXES)
            or re.fullmatch(r"translation_[0-9a-f]{10}_(?:source|provider|(?:model|custom|window|key)_[a-z0-9_]+)", name) is not None)


def _go(page: str):
    """Update the route in a widget callback, before the page is rendered."""
    if st.query_params.get("page", "chart") == "chart" and page != "chart":
        # Hidden widgets are discarded; reports and other non-widget state
        # already survive navigation and must not be restored from a snapshot.
        st.session_state["_chart_workspace_inputs"] = {
            name: value for name, value in st.session_state.items()
            if _is_chart_input(name)
        }
    if page == "chart":
        st.session_state["_chart_workspace_restore"] = True
    st.query_params["page"] = page
    if "preview" in st.query_params:
        del st.query_params["preview"]


def _switch_audience() -> None:
    _go("agent" if st.session_state["ref_audience"] == "代理端" else "chart")



def _source_code() -> str:
    key = "referral_first_source_" + _mode()
    raw = str(st.query_params.get("ref", "")).strip().upper()
    if key not in st.session_state and raw:
        if _store(_demo()).resolve_agent(raw):
            st.session_state[key] = raw
    return st.session_state.get(key, "")



def render_navigation() -> str:
    page = st.query_params.get("page", "chart")
    if page == "admin":
        st.error("此网站不提供该页面。")
        st.stop()
    if page not in ("chart", "agent"):
        page = "chart"
        st.query_params["page"] = page
    if page == "chart" and st.session_state.pop("_chart_workspace_restore", False):
        for name, value in st.session_state.get("_chart_workspace_inputs", {}).items():
            # Filter older snapshots too, so existing sessions can recover.
            if _is_chart_input(name) and name not in st.session_state:
                st.session_state[name] = value
    _source_code()
    st.markdown("""<style>
    .st-key-audience_switch {
        width: 112px !important; max-width: 42%; align-self: flex-end;
        margin-left: auto; margin-bottom: .65rem;
    }
    .st-key-audience_switch div[data-baseweb="select"] > div {
        min-height: 32px; border-radius: 8px; border-color: #303136;
        background: #111317; font-size: .78rem;
    }
    .st-key-audience_switch div[data-baseweb="select"] span {
        font-size: .78rem; color: #b9b2a5;
    }
    </style>""", unsafe_allow_html=True)
    audience = "代理端" if page == "agent" else "客户端"
    if st.session_state.get("ref_audience") != audience:
        st.session_state["ref_audience"] = audience
    with st.container(key="audience_switch"):
        st.selectbox(
            "切换客户端或代理端", ("客户端", "代理端"),
            key="ref_audience", label_visibility="collapsed", on_change=_switch_audience,
        )
    return page



def render_consultation_ticket(plan_id: str, *, key: str, enabled: bool = True, preview_only: bool = False):
    """Create a source-bound ticket only on an explicit customer action."""
    if preview_only:
        st.caption("排盘后的付费解读区域可以生成咨询编号，方便微信联系与推广来源核对。")
        return
    demo = _demo()
    if demo:
        st.caption("本次生成的是演示咨询编号，仅写入独立的演示咨询记录。")
    store = _store(demo)
    ref_code = _source_code()
    source = store.resolve_agent(ref_code) if ref_code else None
    if source:
        st.caption(f"推荐来源：{source['display_name']} · {source['code']}。本次咨询会保留这一来源。")
    elif st.query_params.get("ref") and not ref_code:
        st.info("链接中的推广码未找到有效代理；当前按直接咨询登记。如需核对推荐人，请先联系作者。")
    cache_key = f"ref_ticket_{_mode()}_{key}_{plan_id}_{ref_code}"
    nonce_key = cache_key + "_request"
    if nonce_key not in st.session_state:
        st.session_state[nonce_key] = secrets.token_urlsafe(24)
    ticket = st.session_state.get(cache_key)
    if not ticket and st.button("生成咨询编号", key=cache_key+"_create", type="primary",
                                disabled=not enabled, use_container_width=True):
        try:
            ticket = store.create_lead(st.session_state[nonce_key], plan_id, ref_code)
            st.session_state[cache_key] = ticket
        except ReferralError as error:
            st.error(str(error))
    if ticket:
        with st.container(border=True):
            st.code(f"子平术数咨询｜{ticket['id']}｜{PLAN_NAMES[plan_id]}", language=None)
            st.caption("复制上面这行作为添加好友备注。作者凭咨询编号核对你的需求及推荐来源。")
            st.caption("咨询已登记，尚未确认成交。生成报告、费用和交付安排通过微信沟通。")
            st.write("微信号：**" + WECHAT_ID + "**")



def _table(rows: list[dict], empty: str):
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info(empty)



def _csv(rows: list[dict]) -> bytes:
    target = io.StringIO()
    if rows:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return target.getvalue().encode("utf-8-sig")



@st.cache_data(max_entries=64, show_spinner=False)
def _qr_svg(link: str) -> str:
    import qrcode
    from qrcode.image.svg import SvgPathFillImage
    code = qrcode.QRCode(box_size=5, border=4)
    code.add_data(link)
    code.make(fit=True)
    return code.make_image(image_factory=SvgPathFillImage).to_string().decode("utf-8")



def _share_link(store: PublicStore, code: str) -> str:
    base = store.public_url() or os.environ.get("ZIPING_LOCAL_PREVIEW_URL", "http://127.0.0.1:8501/")
    query = {"page": "chart", "ref": code}
    if store.demo:
        query["demo"] = "1"
    return base.rstrip("/") + "/?" + urlencode(query)


def _change_password(store: PublicStore, token: str):
    with st.form("public_password_change",clear_on_submit=True):
        old = st.text_input("当前密码 / 临时密码",type="password",max_chars=256)
        new = st.text_input("新密码（至少 10 个字符）",type="password",max_chars=256)
        repeated = st.text_input("再次输入新密码",type="password",max_chars=256)
        submitted = st.form_submit_button("保存新密码",type="primary")
    if submitted:
        try:
            if new!=repeated:
                raise ReferralError("两次新密码不一致。")
            st.session_state["public_agent_token_"+_mode()] = store.change_password(token,old,new)
            st.session_state["public_agent_message"] = "密码已更新。"
            st.rerun()
        except ReferralError as error:
            st.error(str(error))


def render_agent_center():
    st.subheader("代理中心")
    st.caption(f"想要加入我们？可以联系作者私人微信：{WECHAT_ID}")
    st.caption("你的推荐，你的业绩。成交与佣金以作者发布的核对结果为准。")
    store = _store(_demo())
    token_key = "public_agent_token_"+_mode()
    if _demo():
        st.info("演示代理查询 · 尚无咨询或成交；等级由独立本机后台发布。")
        choices = store.demo_agents()
        if not choices:
            st.info("尚未收到演示代理资料，请由本机管理工具发布。")
            return
        by_code = {a["code"]:a for a in choices}
        code = st.selectbox("体验代理身份",list(by_code),format_func=lambda v:by_code[v]["display_name"]+" · "+v)
        user = store.identity(st.session_state.get(token_key,""))
        if not user or user["code"]!=code:
            st.session_state[token_key] = store.demo_session(code)
    token = st.session_state.get(token_key,"")
    user = store.identity(token)
    if not user:
        with st.form("public_agent_login",clear_on_submit=True):
            login = st.text_input("代理登录名",max_chars=32)
            password = st.text_input("密码",type="password",max_chars=256)
            submitted = st.form_submit_button("登录代理中心",type="primary",use_container_width=True)
        if submitted:
            try:
                st.session_state[token_key] = store.login(login,password)
                st.rerun()
            except ReferralError as error:
                st.error(str(error))
        st.caption("账号由作者开通。忘记密码请联系作者获取新的临时密码。")
        return
    left,right = st.columns([3,1])
    left.caption("已登录："+user["display_name"])
    with right:
        if st.button("退出登录",use_container_width=True):
            store.logout(token)
            st.session_state.pop(token_key,None)
            st.rerun()
    if user["must_change_password"]:
        st.info("首次登录或密码重置后，请先更换临时密码。")
        _change_password(store,token)
        return
    if message := st.session_state.pop("public_agent_message",None):
        st.success(message)
    if st.button("刷新查询结果"):
        st.rerun()
    try:
        data = store.dashboard(token)
        agent,view = data["agent"],data["view"]
        st.markdown(f"### {agent['grade']} 级代理 · {GRADE_RATES[agent['grade']]/100:g}%")
        st.caption("等级由作者核定；返佣以本机后台登记时锁定的等级及实际净收款计算。")
        ids = {r["id"] for r in view["orders"]}|{r["id"] for r in data["leads"]}
        columns = st.columns(4)
        for col,label,value in zip(columns,("带来咨询","确认成交","待结算佣金","已结算佣金"),
                (len(ids),sum(r["paid"] for r in view["orders"]),_yuan(view["pending_cents"]),_yuan(view["settled_cents"]))):
            col.metric(label,value)
        st.caption("最近发布："+_time(data["published_at"])+"。作者发布新资料后，查询结果才会更新。")
        with st.container(border=True):
            left,right = st.columns([3,1])
            link = _share_link(store,agent["code"])
            with left:
                st.markdown("#### 专属推广链接")
                st.code(link,language=None)
                st.link_button("以客户身份打开",link,use_container_width=True)
                if not store.public_url():
                    st.caption("这是本机预览地址，正式推广前由作者发布公网网址。")
            with right:
                svg = _qr_svg(link)
                st.image(svg,width=150)
                st.download_button("下载二维码",svg.encode(),file_name=agent["code"]+".svg",mime="image/svg+xml")
        orders = {r["id"]:r for r in view["orders"]}
        rows = []
        combined = {r["id"]:r for r in data["leads"]}
        combined.update(orders)
        for cid,row in combined.items():
            confirmed = row.get("paid",False)
            rows.append({"咨询编号":cid,"范围":PLAN_NAMES[row["plan_id"]],
                "状态":"已核对成交" if confirmed else "待作者核对", "净收款":_yuan(row.get("net_cents",0)),
                "佣金":_yuan(row.get("commission_cents",0)),"登记时间":_time(row["created_at"])})
        tabs = st.tabs(["咨询与成交","结算记录"])
        with tabs[0]:
            _table(rows,"还没有咨询。可以先分享链接，客户生成编号后会出现在这里。")
        with tabs[1]:
            _table([{"结算编号":r["id"],"金额":_yuan(r["amount_cents"]),"时间":_time(r["created_at"])} for r in view["settlements"]],"还没有结算记录。")
        if not _demo():
            with st.expander("修改登录密码"):
                _change_password(store,token)
    except ReferralError as error:
        st.error(str(error))

