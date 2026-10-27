"""Customer login and saved chart UI, isolated from agent identities."""
from __future__ import annotations
from datetime import date, datetime, time
import json
import sqlite3
from zoneinfo import ZoneInfo
import streamlit as st
from customer_store import CustomerStore, CustomerError, FORM_KEYS, birth_input_key
from public_security import check_action, PublicSecurityError


@st.cache_resource(show_spinner=False)
def store():
    """Shared account, report, VIP-read and conversation store."""
    return CustomerStore()


def _message(message):
    st.session_state["customer_flash"] = message
    st.rerun()


def _serialize(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    raise TypeError("Unsupported birth input")


def capture_birth_state(form):
    # Called only after a successful chart calculation, never on draft changes.
    payload = {"version": 1, "form": {key: value for key, value in form.items() if key in FORM_KEYS},
               "inputs": {key: value for key, value in st.session_state.items() if birth_input_key(key)}}
    return json.loads(json.dumps(payload, default=_serialize, ensure_ascii=False))


def clear_displayed_birth():
    for key in list(st.session_state):
        if birth_input_key(key) or key in ("chart_result", "birth_form", "saved_birth_state", "retrieval_result", "chart_error", "professional_selection", "professional_transit", "_last_pillar_lookup", "_last_pillar_candidates"):
            st.session_state.pop(key, None)
        elif key.startswith(("v7_basis_auto_", "v7_date_auto_")):
            st.session_state[key] = False
    for key in ("analysis_requested", "analysis_dispatching", "analysis_running"):
        st.session_state[key] = False
    st.session_state.pop("_chart_workspace_inputs", None)


def apply_pending_birth():
    pending = st.session_state.pop("customer_pending_birth", None)
    if not pending:
        return None
    clear_displayed_birth()
    for key, value in pending["inputs"].items():
        if birth_input_key(key):
            st.session_state[key] = time.fromisoformat(value) if key == "birth_time" and value else value
    form = dict(pending["form"])
    if form.get("birth_date"):
        form["birth_date"] = date.fromisoformat(form["birth_date"])
    if form.get("birth_time"):
        form["birth_time"] = time.fromisoformat(form["birth_time"])
    return form



def current_screen():
    default = "chart" if st.session_state.get("chart_result") else "input"
    return st.session_state.get("customer_screen", default)


def _pause_generation():
    for key in list(st.session_state):
        if key.startswith(("v7_basis_auto_", "v7_date_auto_")):
            st.session_state[key] = False


def open_account():
    if current_screen() == "account":
        return
    _pause_generation()
    st.session_state["customer_account_return"] = current_screen()
    if current_screen() == "input":
        st.session_state["customer_draft_inputs"] = {key: value for key,value in st.session_state.items() if birth_input_key(key)}
    st.session_state["customer_screen"] = "account"


def return_to_chart():
    target = st.session_state.get("customer_account_return", "chart")
    if target == "chat" and (st.session_state.get("customer_chat") or st.session_state.get("customer_chat_pending")):
        st.session_state["customer_screen"] = "chat"
        return
    st.session_state["customer_screen"] = "chart" if target == "chart" and st.session_state.get("chart_result") else "input"
    if current_screen() == "chart":
        st.session_state["customer_scroll_chart"] = True
    else:
        st.session_state["customer_restore_inputs"] = True
        st.session_state["customer_restore_draft"] = True


def exit_chart():
    _pause_generation()
    st.session_state["customer_screen"] = "input"
    st.session_state["customer_restore_inputs"] = True
    st.session_state["customer_dialog"] = None


def restore_input_form():
    if not st.session_state.pop("customer_restore_inputs", False):
        return
    values = st.session_state.get("saved_birth_state", {}).get("inputs", {})
    if st.session_state.pop("customer_restore_draft", False):
        values = st.session_state.get("customer_draft_inputs") or values
    for key, value in values.items():
        if birth_input_key(key):
            st.session_state[key] = time.fromisoformat(value) if key == "birth_time" and isinstance(value,str) else value


def logout_customer():
    store().logout(st.session_state.get("customer_token", ""))
    for key in ("customer_token", "customer_recovery", "customer_pending_birth", "customer_save_after_login", "customer_draft_inputs", "customer_restore_inputs", "customer_restore_draft"):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith(("customer_chat", "chat_")):
            st.session_state.pop(key,None)
    clear_displayed_birth()
    st.session_state["customer_screen"] = "input"
    st.session_state["customer_dialog"] = None
    st.session_state["customer_flash"] = "已退出账号，当前出生资料已清空。"


def request_save_chart():
    if store().identity(st.session_state.get("customer_token", "")):
        st.session_state["customer_dialog"] = "save"
    else:
        st.session_state["customer_dialog"] = "login"
        st.session_state["customer_save_after_login"] = True


def dismiss_customer_dialog():
    st.session_state["customer_dialog"] = None
    st.session_state.pop("customer_save_after_login", None)


def _recovery_notice():
    recovery = st.session_state.get("customer_recovery")
    if not recovery:
        return
    st.warning("请妥善保存下面的恢复码。忘记密码时需要它；关闭后无法再次查看。")
    st.caption("账号："+recovery["username"])
    st.code(recovery["code"], language=None)
    if st.button("我已保存恢复码", key="customer_recovery_saved"):
        st.session_state.pop("customer_recovery", None)
        st.rerun()


@st.dialog("登录 / 注册", width="small", on_dismiss=dismiss_customer_dialog)
def _login_dialog():
    st.caption("登录后即可保存当前命盘。关闭弹窗不会丢失这次排盘。")
    render_customer_account(in_dialog=True)


@st.dialog("保存排盘", width="small", on_dismiss=dismiss_customer_dialog)
def _save_dialog():
    _recovery_notice()
    result = st.session_state.get("chart_result")
    if result:
        render_save_chart(result["chart"])
    else:
        st.info("请先完成排盘。")


def render_customer_header():
    try:
        user = store().identity(st.session_state.get("customer_token", ""))
        if user and st.session_state.get("customer_dialog") == "login":
            st.session_state["customer_dialog"] = "save" if st.session_state.pop("customer_save_after_login", False) else None
        st.markdown("""<style>
        .st-key-customer_header{margin-left:auto;max-width:360px}
        .st-key-customer_header button{font-size:13px;min-height:34px;padding:4px 12px}
        .st-key-customer_header [data-testid=stCaptionContainer]{padding-top:7px}
        </style>""", unsafe_allow_html=True)
        with st.container(key="customer_header",horizontal=True,horizontal_alignment="right",vertical_alignment="center"):
            if user:
                st.button("我的排盘 · "+user["username"],key="customer_header_account",on_click=open_account)
                st.button("退出登录",key="customer_header_logout",on_click=logout_customer)
            else:
                st.button("登录 / 注册",key="customer_header_login",on_click=open_account)
        with st.container(key="customer_global_feedback"):
            if current_screen() != "account":
                if message := st.session_state.pop("customer_flash", None):
                    st.success(message)
        dialog = st.session_state.get("customer_dialog")
        if dialog == "login" and not user:
            _login_dialog()
        elif dialog == "save" and user:
            _save_dialog()
    except (CustomerError, PublicSecurityError) as error:
        st.error(str(error))
    except (OSError, sqlite3.Error):
        st.error("用户资料暂时不可用；仍可使用游客排盘。")


def render_customer_account(*, in_dialog=False):
    try:
        service = store()
        token = st.session_state.get("customer_token", "")
        user = service.identity(token)
        recovery = st.session_state.get("customer_recovery")
        title = "我的排盘 · "+user["username"] if user else "我的排盘 · 登录 / 注册"
        if st.session_state.pop("customer_show_reports", False):
            st.session_state["customer_account_view"] = "报告收藏"
        with st.container(border=not in_dialog, key="customer_account_page"):
            if not in_dialog:
                st.subheader(title if user else "登录 / 注册")
                st.button("返回排盘", key="customer_account_back", on_click=return_to_chart)
            st.caption("游客可直接排盘；登录后可保存并重新打开。普通用户账号与代理账号独立。")
            # Stable slots prevent feedback appearing/disappearing from moving
            # the account navigation and leaving faded old blocks on a rerun.
            with st.container(key="customer_account_feedback"):
                if message := st.session_state.pop("customer_flash", None):
                    st.success(message)
            with st.container(key="customer_account_recovery"):
                _recovery_notice()
            if user:
                vip=service.vip_status(token)
                expires="长期有效" if vip['expires'] is None else datetime.fromtimestamp(vip['expires'],ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
                st.caption("VIP："+("有效 · "+expires if vip['active'] else "未开通或已到期，报告追问需联系作者人工开通"))
                if st.session_state.get("customer_account_view") not in ("我的排盘", "报告收藏", "我的对话"):
                    previous = st.session_state.get("customer_account_tab")
                    st.session_state["customer_account_view"] = previous if previous in ("我的排盘", "报告收藏", "我的对话") else "我的排盘"
                view = st.segmented_control("账号内容", ["我的排盘", "报告收藏", "我的对话"],
                                             key="customer_account_view", required=True, label_visibility="collapsed")
                with st.container(key="customer_account_content"):
                    if view == "报告收藏":
                        from customer_reports import render_report_library
                        render_report_library(service, token)
                    elif view == "我的对话":
                        from report_chat_panel import render_conversation_library
                        render_conversation_library(service, token)
                    else:
                        _render_library(service, token)
                if st.button("退出用户账号", key="customer_logout"):
                    logout_customer()
                    st.rerun()
            else:
                login_tab, register_tab, recover_tab = st.tabs(["登录", "注册", "找回密码"], key="customer_auth_tab", on_change="rerun")
                with login_tab:
                    with st.form("customer_login", clear_on_submit=True):
                        username = st.text_input("用户名", max_chars=32, key="customer_login_name")
                        password = st.text_input("密码", type="password", max_chars=128, key="customer_login_password")
                        submit = st.form_submit_button("登录我的排盘", type="primary", use_container_width=True)
                    if submit:
                        check_action("login")
                        st.session_state["customer_token"] = service.login(username, password)
                        _message("登录成功，已保存的排盘会显示在这里。")
                with register_tab:
                    with st.form("customer_register", clear_on_submit=True):
                        username = st.text_input("设置用户名", max_chars=32, help="3至32位英文字母、数字、点、横线或下划线。")
                        password = st.text_input("设置密码", type="password", max_chars=128, help="至少10位。")
                        confirmation = st.text_input("再次输入密码", type="password", max_chars=128)
                        consent = st.checkbox("我同意保存的出生资料仅用于我的排盘，并知晓可自行删除；请勿未经同意保存他人资料。")
                        submit = st.form_submit_button("注册并登录", type="primary", use_container_width=True)
                    if submit:
                        check_action("customer_register")
                        if not consent:
                            raise CustomerError("请先勾选出生资料保存说明。")
                        if password != confirmation:
                            raise CustomerError("两次输入的密码不一致。")
                        token, code = service.register(username, password)
                        st.session_state["customer_token"] = token
                        st.session_state["customer_recovery"] = {"username":username.strip().lower(), "code":code}
                        _message("注册成功。保存排盘不会自动保存AI报告；需要时可单独收藏报告。不保存模型 API Key。")
                with recover_tab:
                    st.caption("使用注册时保存的恢复码重设密码。成功后旧登录会话和旧恢复码失效，请保管新恢复码。")
                    with st.form("customer_recover", clear_on_submit=True):
                        username = st.text_input("需要找回的用户名", max_chars=32)
                        code = st.text_input("恢复码", type="password", max_chars=128)
                        password = st.text_input("新密码", type="password", max_chars=128)
                        confirmation = st.text_input("再次输入新密码", type="password", max_chars=128)
                        submit = st.form_submit_button("重设密码")
                    if submit:
                        check_action("password")
                        if password != confirmation:
                            raise CustomerError("两次输入的新密码不一致。")
                        next_code = service.recover(username, code.strip(), password)
                        st.session_state.pop("customer_token", None)
                        st.session_state["customer_recovery"] = {"username":username.strip().lower(),"code":next_code}
                        _message("密码已重设，请使用新密码登录，并保存新的恢复码。")
    except (CustomerError, PublicSecurityError) as error:
        st.error(str(error))
    except (OSError, sqlite3.Error):
        st.error("用户资料暂时无法读取或保存，请稍后重试。")


def _render_library(service, token):
    rows = service.list_charts(token)
    st.caption(f"已保存 {len(rows)} / 100 份 · 修改输入后需重新排盘，再保存新结果。")
    if not rows:
        st.info("还没有保存排盘。先在下方排盘，再点击“保存这份排盘”。")
        return
    by_id = {r["id"]:r for r in rows}
    selection_key = "customer_library_selection"
    if st.session_state.get(selection_key) not in by_id:
        st.session_state.pop(selection_key, None)
    cid = st.selectbox("选择已保存的排盘", list(by_id), format_func=lambda cid: by_id[cid]["title"]+" · "+by_id[cid]["summary"], key=selection_key)
    item = by_id[cid]
    st.caption(item["summary"])
    stamp = datetime.fromtimestamp(item["updated"], ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    st.caption("最近保存："+stamp)
    if item["note"]:
        st.text(item["note"])
    if st.button("打开这份排盘", key="customer_open_chart", type="primary", use_container_width=True):
        check_action("chart")
        st.session_state["customer_pending_birth"] = service.load(token, cid)
        st.session_state["customer_screen"] = "chart"
        _message("已打开保存的出生资料，并按当前排盘规则重新计算。")
    if st.button("查看这份排盘的收藏报告", key="customer_chart_reports", use_container_width=True):
        st.session_state["customer_report_filter_chart"] = cid
        st.session_state["customer_report_filter_all"] = False
        st.session_state["customer_report_selection"] = None
        st.session_state["customer_show_reports"] = True
        _message("已切换到这份排盘关联的报告收藏。")
    with st.expander("修改名称 / 删除这份排盘"):
        with st.form("customer_edit_"+cid):
            title = st.text_input("排盘名称", value=item["title"], max_chars=40)
            note = st.text_area("备注", value=item["note"], max_chars=300)
            rename = st.form_submit_button("保存名称与备注")
        if rename:
            check_action("customer_save")
            service.save(token,title,note,item["summary"],service.load(token,cid))
            _message("名称与备注已保存。")
        with st.form("customer_delete_"+cid, clear_on_submit=True):
            st.caption("删除排盘不会自动删除报告收藏；报告可在“报告收藏”中单独删除。")
            confirmed = st.checkbox("确认删除这份已保存的排盘")
            delete = st.form_submit_button("删除这份排盘")
        if delete:
            check_action("customer_save")
            if not confirmed:
                raise CustomerError("请先勾选确认删除。")
            service.delete(token,cid)
            _message("这份排盘已从账号中删除。")


def render_save_chart(chart):
    try:
        service=store()
        token=st.session_state.get("customer_token", "")
        if not service.identity(token):
            st.caption("想保留这份命盘？在页面上方“我的排盘”注册或登录后即可保存。")
            return
        payload=st.session_state.get("saved_birth_state")
        if not payload:
            st.caption("请重新点击“开始排盘”，然后即可保存这份排盘。")
            return
        pillars="　".join(chart["四柱"].values())
        summary=pillars+" · "+str(chart.get("性别", ""))+" · "+str(chart.get("输入出生时间") or chart.get("专业出生时刻") or "四柱输入")
        with st.container(key="customer_save_body"):
            st.caption("此处只保存出生资料、地点和排盘选项，不保存模型密钥或咨询信息。AI报告可在下载区单独收藏。同一出生资料重复保存会更新已有记录。")
            with st.form("customer_save_chart", clear_on_submit=True):
                title=st.text_input("排盘名称（称呼）", value="我的命盘", max_chars=40)
                note=st.text_area("备注（选填）", max_chars=300)
                consent=st.checkbox("确认将这份出生资料保存到我的账号")
                submit=st.form_submit_button("保存到我的排盘", type="primary", use_container_width=True)
            if submit:
                check_action("customer_save")
                if not consent:
                    raise CustomerError("请先勾选确认保存出生资料。")
                service.save(token,title,note,summary,payload)
                st.session_state["customer_dialog"] = None
                _message("排盘已保存，可在页面上方“我的排盘”重新打开。")
    except (CustomerError, PublicSecurityError) as error:
        st.error(str(error))
    except (OSError, sqlite3.Error):
        st.error("排盘暂时无法保存，请稍后重试。")
