"""Two reading editions of the same report. No API calls and no score changes."""
from __future__ import annotations
import html
import base64
from html.parser import HTMLParser

STYLE = """
.reader{color:#e9e4da;font:16px/1.95 sans-serif;overflow-wrap:anywhere}
.reader h2,.reader h3,.reader h4{color:#e5ca99;font-family:serif;line-height:1.6}
.reader h2{font-size:26px}.reader h3{font-size:22px;margin:0 0 12px}.reader h4{font-size:17px;margin:8px 0}
.reader-section{padding:24px;border:1px solid #393a40;border-radius:14px;background:#15171b;margin:18px 0}
.reader-lead{font-size:19px;color:#f1e5d0;margin-top:0}.reader-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.reader-card{padding:16px;background:#1d1e23;border-radius:10px;border:1px solid #34353b}.reader p{margin:9px 0}
.reader-label{color:#d3b780}.reader-note{font-size:13px;color:#b3aca1}.reader-year{border-top:1px solid #35353b;padding:12px 0}
.reader details{margin:14px 0}.reader summary{cursor:pointer;color:#d3b780}.reader li{margin:6px 0}
.reader-example{padding:14px;border:1px dashed #8e774c;border-radius:9px;color:#e1c79a;font-size:14px}
@media(max-width:600px){.reader-section{padding:16px}.reader-grid{grid-template-columns:1fr}.reader{font-size:15px}.reader-lead{font-size:18px}}
"""


def _escape(value):
    return html.escape(str(value or ""), quote=True)


def _p(value, css=""):
    return '<p'+(' class="'+css+'"' if css else '')+'>'+_escape(value).replace('\n','<br>')+'</p>'


def _score(value):
    return "暂不评分" if value is None else f"{value:g} / 100"


def _section(document, title):
    from report_presentation import presentation_view
    view = presentation_view(document)
    plain = document.get("plain_language")
    full = isinstance(plain,dict) and all(isinstance(plain.get(k),str) and plain[k].strip() for k in ("summary","why","opportunity","caution","conditions"))
    out=['<section class="reader-section"><h3>'+_escape(title)+'</h3>']
    if not full:
        out.append(_p("这份旧报告没有完整的小白版。下面仅展示原有摘要；详细依据请切换专业版。不会自动调用模型补写。","reader-note"))
    out.append(_p(plain['summary'] if full else view['overview']['headline'],"reader-lead"))
    if full:
        out+=['<h4>为什么这样说</h4>',_p(plain['why'])]
    out.append('<div class="reader-grid">')
    for card in view['cards']:
        label={"career":"事业与学业","wealth":"钱与资源","relationship":"感情与相处"}.get(card['key'],card['label'])
        out+=['<article class="reader-card"><h4>'+_escape(label)+'</h4>',_p(card['summary'])]
        if card['advice']:
            out.append(_p('可以这样做：'+card['advice']))
        out.append('</article>')
    out.append('</div>')
    for key,label in (("opportunity","可以把握什么"),("caution","要留意什么")):
        text=plain.get(key) if full else view['overview'].get(key)
        if text:
            out+=['<h4>'+label+'</h4>',_p(text)]
    if full:
        out+=['<h4>接下来可以怎么做</h4>','<ol>'+''.join('<li>'+_escape(item)+'</li>' for item in plain.get('actions',[]) if isinstance(item,str))+'</ol>',
              '<h4>这些话在什么情况下才适用</h4>',_p(plain['conditions'])]
    if 'score' in document:
        out.append(_p('参考指数：'+_score(document['score'])+'。与专业版完全相同，用于对照这份报告，不是成功率。','reader-note'))
    years=document.get('years',[])
    if years:
        out.append('<details><summary>逐年看看：哪几年更顺，哪几年要多做准备</summary>')
        for year in years:
            out+=['<div class="reader-year"><h4>'+_escape(year['year'])+'年 · '+_score(year.get('score'))+'</h4>',
                  _p(year.get('plain_reason') or '这份报告未单独记录这一年的白话说明，请切换专业版查看原评分依据。'),'</div>']
        out.append('</details>')
    return ''.join(out)+'</section>'


def _period_title(item):
    selected=item.get('selected',{})
    if item.get('id')=='annual':
        return str(selected.get('流年',{}).get('年份','所选'))+'年：这一年的重点'
    if item.get('id')=='monthly':
        month=selected.get('流月',{})
        return '这段时间：'+str(month.get('起始时刻',''))[:10]+' 至 '+str(month.get('结束时刻',''))[:10]
    return '这一天：'+str(selected.get('流日',{}).get('日期','所选日期'))


def beginner_html(report, *, example=False):
    out=['<style>'+STYLE+'</style><div class="reader">']
    if example:
        out.append('<div class="reader-example">文风与排版示例：内容及分数为人工编写的虚构演示，不是你的命盘分析，也不是模型实际生成的报告。</div>')
    out.append(_p('小白版 · 先看生活中的意思，再决定是否查看专业推导。','reader-note'))
    if report.get('kind')=='period-only':
        for item in report.get('periods',[]):
            out.append(_section(item,_period_title(item)))
    else:
        life=report.get('luck_analysis') or {}
        if life.get('cycles'):
            from luck_chart import chart_svg
            chart_image = '<img alt="子平K线：与专业版相同的大运和年度参考分" style="width:100%;min-width:680px;display:block" src="data:image/svg+xml;base64,'+base64.b64encode(chart_svg(life).encode('utf-8')).decode('ascii')+'">'
            out.append('<section class="reader-section reader-kline"><h3>先看整体节奏：子平K线</h3>'
                       +_p('每根柱代表一步十年大运，金点表示总体参考分；柱体两端对应首末年份，细线表示这十年里的最高与最低分。','reader-note')
                       +'<div style="overflow-x:auto">'+chart_image+'</div>'
                       +_p('分数直接沿用专业版，不另外打分；它不是成功率，也不是收入走势图。','reader-note')+'</section>')
        out.append(_section(report,'先认识自己：适合怎样做事'))
        for item in life.get('cycles',[]):
            cycle=item['cycle']
            title=f"{cycle['start_year']}—{cycle['end_year']}：这十年的大致节奏"
            out.append(_section(item,title))
        for item in life.get('selected',[]):
            out.append(_section(item,_period_title(item)))
    out.append(_p('国学教育，仅供娱乐。这里是有条件的传统命理解读，不能替代你对现实情况的判断。','reader-note'))
    return ''.join(out)+'</div>'


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
        self.ignored=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('style','script','svg'):
            self.ignored.append(tag)
        elif not self.ignored and tag in ('p','h2','h3','h4','li','summary','br'):
            self.parts.append('\n')
    def handle_endtag(self,tag):
        if self.ignored:
            if tag==self.ignored[-1]:self.ignored.pop()
        elif tag in ('p','li','h3','h4'):
            self.parts.append('\n')
    def handle_data(self,data):
        if not self.ignored:self.parts.append(data)


def beginner_text(report, *, example=False):
    parser=_PlainText()
    parser.feed(beginner_html(report,example=example))
    return ''.join(parser.parts).strip()


def render_reading_edition(report,sources,*,key,example=False):
    import streamlit as st
    edition=st.segmented_control('阅读版本',['小白版','专业版'],default='小白版',required=True,key='reading_edition_'+key)
    if edition=='小白版':
        st.html(beginner_html(report,example=example))
        return 'beginner'
    if example:
        st.warning('这是人工编写的虚构示例，分数仅供演示，不是你的命盘分析。')
    from luck_chart import render_extended
    render_extended(report,sources,key=key)
    return 'professional'
