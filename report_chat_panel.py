"""Dedicated report chat page; credentials and unsaved chat stay in this session."""
from __future__ import annotations
import json,sqlite3,re
from datetime import datetime,timedelta,date
from zoneinfo import ZoneInfo
import streamlit as st
from customer_store import CustomerError
from public_security import PublicSecurityError,check_action
from report_chat import build_snapshot,validate_snapshot,validate_history,answer_question


def open_report_chat(text,title,*,return_screen='chart',report_id=None):
    from customer_panel import _pause_generation
    snapshot=build_snapshot(text,title)
    _pause_generation()
    st.session_state['customer_chat_pending']={'snapshot':snapshot,'return_screen':return_screen,'report_id':report_id}
    st.session_state['customer_screen']='chat'
    st.rerun()


def _activate(pending,user):
    st.session_state['customer_chat']={'snapshot':pending['snapshot'],'messages':[], 'title':pending['snapshot']['title'][:80],
                                      'saved_id':None,'owner':user['id'],'return_screen':pending.get('return_screen','account'),
                                      'report_id':pending.get('report_id')}
    st.session_state.pop('customer_chat_pending',None)
    st.session_state.pop('chat_autosave',None)
    st.session_state.pop('chat_question',None)
    st.session_state.pop('chat_new_confirm',None)


def _new_chat():
    from customer_panel import store
    state=st.session_state['customer_chat']
    user=store().identity(st.session_state.get('customer_token',''))
    if user:
        _activate({'snapshot':state['snapshot'],'return_screen':state.get('return_screen'),'report_id':state.get('report_id')},user)
        st.session_state.pop('chat_title_'+state['snapshot']['fingerprint'],None)


def _return():
    state=st.session_state.get('customer_chat',{})
    pending=st.session_state.get('customer_chat_pending',{})
    target=pending.get('return_screen','account') if pending else state.get('return_screen','account')
    st.session_state['customer_screen']='chart' if target=='chart' and st.session_state.get('chart_result') else 'account'
    if st.session_state['customer_screen']=='account':
        report_id=pending.get('report_id') if pending else state.get('report_id')
        st.session_state['customer_account_view']='报告收藏' if report_id else '我的对话'
        if report_id:st.session_state['customer_report_selection']=report_id


def _save(service,token,state):
    check_action('customer_save')
    state['saved_id']=service.save_conversation(token,state.get('saved_id'),state['title'],state['snapshot'],state['messages'])


def _messages(state):
    chunks={p['id']:p['text'] for p in state['snapshot']['chunks']}
    for index,message in enumerate(state['messages']):
        with st.chat_message(message['role']):
            if message.get('sent_at'):st.caption(message['sent_at'].replace('T',' '))
            if message.get('time_scope'):
                st.caption('时间范围：'+'；'.join(kind+'：'+('、'.join(values) if values else '全部') for kind,values in message['time_scope'].items()))
            st.text(message['content'])
            if message.get('source_note'):st.caption(message['source_note'])
            if message['citations']:
                with st.expander('查看出处与原文依据',expanded=False):
                    for ref in message['citations']:
                        st.caption('出处 ['+ref['id']+']')
                        labels=re.findall(r'《[^《》\n]{1,50}》[^\n]{0,100}',chunks[ref['id']])
                        st.caption('该报告段落记载的古籍出处：'+'；'.join(dict.fromkeys(labels)) if labels else '出处类型：报告分析；本段未记载可直接核对的古籍书名、章节及行号。')
                        st.text('出处段落原文片段：'+ref['quote'])
                        st.text(chunks[ref['id']])
            if message['role']=='assistant' and not message['citations']:
                st.caption('本次未引用报告原句；补充说明不应当作报告已有结论。')


def _time_selector(snapshot):
    from professional_chart import flow_months
    text='\n'.join(c['text'] for c in snapshot['chunks'])
    cycles={}
    for match in re.finditer(r'(?m)^([^\n]{0,48}?[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]\s*[·：:]?\s*((?:19|20|21)\d{2})[—–－-]((?:19|20|21)\d{2}))',text):
        label=match[1].strip();start,end=int(match[2]),int(match[3])
        if start<=end<=start+12:cycles[label]=list(range(start,end+1))
    def choose(label,options):
        key='chat_scope_'+snapshot['fingerprint']+'_'+label
        if key in st.session_state:
            st.session_state[key]=[v for v in st.session_state[key] if v in options]
        return st.multiselect(label,options,key=key,placeholder='不选即不限此层级')
    st.markdown('#### 本轮时间范围')
    st.caption('按大运 → 年 → 月 → 日选择，各项均可多选。每项内部取并集，不同项共同限定；全部不选即整份报告。流月按节气划分。')
    selected_cycles=choose('大运',list(cycles))
    if not cycles:st.caption('报告中未识别出大运起止年，可直接选择年月日；不会因此新算大运。')
    years=sorted({y for c in selected_cycles for y in cycles[c]}) if selected_cycles else list(range(1900,2201))
    selected_years=choose('年',[str(y) for y in years])
    months={}
    for year in selected_years:
        for month in flow_months(int(year),'甲'):
            label=f"{year}年{month['label']} · {month['start'][:10]}—{month['end'][:10]}"
            months[label]=month
    month_options=list(months) if selected_years else [b+'月' for b in '寅卯辰巳午未申酉戌亥子丑']
    selected_months=choose('月',month_options)
    days=set()
    if selected_years:
        if selected_months:
            for label in selected_months:
                month=months[label];current=date.fromisoformat(month['start'][:10]);end=datetime.fromisoformat(month['end'])
                while datetime.combine(current,datetime.min.time())<end:
                    days.add(current.isoformat());current+=timedelta(days=1)
        else:
            for year in selected_years:
                current=date(int(year),1,1)
                while current.year==int(year):
                    days.add(current.isoformat());current+=timedelta(days=1)
    selected_days=choose('日',sorted(days))
    if not selected_years:st.caption('选择具体年份后可多选日期；不选年份时，所选节月适用于全部年份。交节日需结合具体交节时刻理解。')
    return {'大运':selected_cycles,'年':selected_years,'月':selected_months,'日':selected_days}


def render_report_chat():
    from customer_panel import store,open_account
    from referral_common import WECHAT_ID
    try:
        service=store(); token=st.session_state.get('customer_token',''); user=service.identity(token)
        if st.session_state.pop('chat_clear_question',False):st.session_state.pop('chat_question',None)
        st.subheader('问问AI')
        st.button('返回报告',key='chat_back',on_click=_return)
        if not user:
            st.info('请先登录，再核对VIP资格。当前报告不会因此丢失。')
            st.button('登录 / 注册',key='chat_login',on_click=open_account)
            return
        pending=st.session_state.get('customer_chat_pending')
        state=st.session_state.get('customer_chat')
        if state and state.get('owner')!=user['id']:
            st.session_state.pop('customer_chat',None);state=None
        vip=service.vip_status(token)
        if pending:
            if not vip['active']:
                st.info('报告追问功能仅向VIP开放，请联系作者人工开通。')
                st.text('作者微信：'+WECHAT_ID)
                st.caption('VIP由作者人工开通，只包含功能权限。模型Token费用由你的API账户承担，不含人工解读。')
                return
            if state and state['messages'] and not state.get('saved_id') and state['snapshot']['fingerprint']!=pending['snapshot']['fingerprint']:
                st.warning('当前对话尚未保存。切换报告前可以先保存，或确认不保留这段会话。')
                if st.button('先保存当前对话',key='chat_save_before_switch'):
                    _save(service,token,state);st.rerun()
                if st.button('确认切换报告并开始新对话',key='chat_confirm_switch'):
                    _activate(pending,user);st.rerun()
                return
            if not state or state['snapshot']['fingerprint']!=pending['snapshot']['fingerprint']:
                _activate(pending,user);state=st.session_state['customer_chat']
            else:st.session_state.pop('customer_chat_pending',None)
        if not state:
            st.info('请先从报告下载区或报告收藏中点击“问问AI”。')
            return
        validate_snapshot(state['snapshot']);validate_history(state['messages'],state['snapshot'])
        st.caption('当前报告：'+state['snapshot']['title']+' · 版本 '+state['snapshot']['fingerprint'][:10])
        st.caption('结合原局与所选时间干支关系回答实际问题；报告及原文依据折叠展示。本轮推演与报告既有结论分开说明。')
        if state['snapshot'].get('natal_facts',{}).get('四柱'):
            st.caption('绑定原局：'+state['snapshot']['natal_facts']['四柱'])
        with st.expander('查看本次绑定的报告版本'):
            for chunk in state['snapshot']['chunks']:
                st.text('['+chunk['id']+'] '+chunk['text'])
        if state['snapshot']['truncated']:
            st.warning('这是旧版截取的报告快照。请返回完整报告，重新点击“问问AI”绑定全文；旧对话内容仍可保存查看。')
        else:st.caption(f"报告正文已完整保留，共{len(state['snapshot']['chunks'])}个引用片段；每轮将全文提供给模型，超出上下文容量时会明确提示，不自动截断。")
        if state['snapshot']['version']<3:st.caption('本对话绑定的是旧版正文起点。若需从“查看完整推导与古籍依据”重新绑定，请从原报告重新进入问答。')
        with st.expander('对话保存设置',expanded=False):
            state['title']=st.text_input('对话名称',value=state['title'],max_chars=80,key='chat_title_'+str(state.get('saved_id') or state['snapshot']['fingerprint']))
            auto=st.checkbox('自动保存本次对话到账号',key='chat_autosave',help='勾选后每次新回答自动保存；已有内容可点击保存对话。API Key不随对话保存。')
            if st.button('保存对话',key='chat_save'):
                _save(service,token,state);st.success('对话已保存，可在“我的排盘 → 我的对话”继续查看。')
            st.caption('每个账号最多20段已保存对话，每段最多50条消息，总空间10MB。未保存对话关闭会话后可能丢失。')
            if state.get('saved_id'):st.caption('本段对话已保存；新增消息仍需手动保存或启用自动保存。')
            confirmed=st.checkbox('我已保存当前对话，或确认不保留后续未保存内容',key='chat_new_confirm')
            st.button('新建同报告对话',key='chat_new',disabled=bool(state['messages']) and not confirmed,on_click=_new_chat)
        if state['snapshot']['truncated']:
            st.info('请先从原报告重新进入问答页，恢复完整正文后再发送问题。')
            _messages(state)
            return
        if not vip['active']:
            st.info('VIP资格已失效；仍可查看、下载或删除自己的已保存对话。发送新问题需重新开通。')
            st.text('作者微信：'+WECHAT_ID)
            _messages(state)
            return
        from ai_analysis import PROVIDERS,AIError
        with st.expander('使用我的模型',expanded=True):
            provider=st.selectbox('问答模型平台',list(PROVIDERS),format_func=lambda p:PROVIDERS[p]['name'],key='chat_provider')
            model=st.selectbox('问答模型',list(PROVIDERS[provider]['models']),key='chat_model_'+provider)
            api_key=st.text_input('我的API Key',type='password',key='chat_api_key_'+provider)
            st.caption('仅使用你在这里填写的密钥，不读取作者密钥；每次问答会产生模型Token用量。')
        scope=_time_selector(state['snapshot'])
        st.caption('当前时间（北京时间）：'+datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')+'；每轮发送时记录实际时间和本轮选择。')
        with st.form('chat_question_form',clear_on_submit=False):
            question=st.text_area('你实际遇到了什么问题？',max_chars=2000,key='chat_question',placeholder='例如：最近有两个工作方向，我应该先核对哪些现实条件？')
            submitted=st.form_submit_button('发送问题',type='primary',disabled=not bool(api_key) or len(state['messages'])>=50)
        if submitted:
            try:
                with st.spinner('正在结合报告回答…'):
                    state['messages']=answer_question(service,token,state['snapshot'],state['messages'],question,api_key=api_key,provider=provider,model=model,time_scope=scope)
                st.session_state['chat_clear_question']=True
                if auto:
                    try:_save(service,token,state)
                    except (CustomerError,PublicSecurityError,sqlite3.Error,OSError) as error:
                        st.session_state['customer_chat_save_warning']='本轮回答已保留在当前会话，但自动保存未完成，请手动保存。'
                st.rerun()
            except (AIError,CustomerError,PublicSecurityError) as error:st.error(str(error))
        if warning:=st.session_state.pop('customer_chat_save_warning',None):st.warning(warning)
        if state['messages']:
            st.markdown('#### 对话记录')
            _messages(state)
    except (CustomerError,PublicSecurityError) as error:st.error(str(error))
    except (OSError,sqlite3.Error):st.error('对话资料暂时不可用，请稍后重试。')


def render_conversation_library(service,token):
    rows=service.list_conversations(token)
    st.caption(f'已保存 {len(rows)} / 20 段。VIP失效后仍可查看、下载和删除。')
    if not rows:st.info('还没有保存的对话。报告后点击“问问AI”，可选择保存。');return
    by_id={r['id']:r for r in rows};key='customer_conversation_selection'
    if st.session_state.get(key) not in by_id:st.session_state.pop(key,None)
    cid=st.selectbox('选择已保存对话',list(by_id),format_func=lambda cid:by_id[cid]['title'],key=key)
    row=service.load_conversation(token,cid)
    validate_snapshot(row['snapshot']);validate_history(row['messages'],row['snapshot'])
    st.caption('绑定报告：'+row['snapshot']['title']+' · '+row['snapshot']['fingerprint'][:10])
    st.caption('保存时间：'+datetime.fromtimestamp(row['updated'],ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M'))
    if st.button('打开这段对话',key='customer_conversation_open',type='primary'):
        user=service.identity(token)
        st.session_state['customer_chat']={'snapshot':row['snapshot'],'messages':row['messages'],'title':row['title'],'saved_id':cid,'owner':user['id'],'return_screen':'account'}
        st.session_state.pop('customer_chat_pending',None);st.session_state.pop('chat_autosave',None)
        st.session_state['customer_screen']='chat';st.rerun()
    with st.expander('查看已保存的消息'):_messages(row)
    text='报告：'+row['snapshot']['title']+'\n版本：'+row['snapshot']['fingerprint']+'\n\n'
    for message in row['messages']:
        if message.get('sent_at'):text+='时间：'+message['sent_at']+'\n'
        if message.get('time_scope'):text+='本轮范围：'+json.dumps(message['time_scope'],ensure_ascii=False)+'\n'
        text+=('我' if message['role']=='user' else 'AI')+'：'+message['content']+'\n'
        if message.get('source_note'):text+='出处核对说明：'+message['source_note']+'\n'
        for ref in message['citations']:text+='报告依据 ['+ref['id']+'] '+ref['quote']+'\n'
        text+='\n'
    st.download_button('下载对话TXT',text.encode('utf-8-sig'),file_name='子平术数-对话记录.txt',mime='text/plain',key='customer_conversation_download')
    with st.form('customer_conversation_delete_'+cid):
        confirmed=st.checkbox('确认删除这段已保存对话')
        delete=st.form_submit_button('删除对话')
    if delete:
        if not confirmed:raise CustomerError('请勾选确认删除。')
        check_action('customer_save');service.delete_conversation(token,cid)
        if st.session_state.get('customer_chat',{}).get('saved_id')==cid:st.session_state.pop('customer_chat',None)
        st.session_state['customer_flash']='对话已删除，原报告不受影响。';st.rerun()
