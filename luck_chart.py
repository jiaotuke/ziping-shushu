"""Code-drawn, offline SVG chart and escaped views shared by reports and Android."""

from __future__ import annotations

import html

from luck_analysis import FACTORS, SCORE_NOTE


def esc(value):
    return html.escape(str(value), quote=True)


def score_label(value):
    return "证据不足，暂不评分" if value is None else f"{value:g} / 100"


def chart_svg(life):
    cycles = life["cycles"]
    width, height = max(920, len(cycles) * 86 + 80), 350
    y = lambda score: 35 + (100 - score) * 2.4
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="人生K线，项目解释性评分" viewBox="0 0 {width} {height}" style="width:100%;min-width:850px;font-family:serif;background:#101114;color:#ddd">',
             '<desc>每步大运一根K线，开收为首末流年评分，高低为该运全部流年评分极值，金点为大运综合分。缺分不补点。</desc>']
    for tick in (0, 25, 50, 75, 100):
        parts.append(f'<path d="M45 {y(tick)}H{width-15}" stroke="#34343b"/><text x="7" y="{y(tick)+5}" fill="#aaa" font-size="13">{tick}</text>')
    for i, item in enumerate(cycles):
        x = 85 + i * (width - 115) / max(len(cycles), 1)
        cycle, candle = item["cycle"], item["ohlc"]
        title = f"{cycle['label']} {cycle['pillar']} · {cycle['start_year']}—{cycle['end_year']} · {cycle['note']}\n综合：{score_label(item['score'])}"
        if candle:
            title += f"\n开 {candle['open']} / 收 {candle['close']} / 高 {candle['high']} / 低 {candle['low']}"
        else:
            title += "\n年度评分有缺项，不生成完整蜡烛"
        parts.append(f'<g><title>{esc(title)}</title>')
        if candle:
            color = "#66b69a" if candle["close"] >= candle["open"] else "#df8875"
            top = y(max(candle["open"], candle["close"]))
            body = max(2, abs(y(candle["open"]) - y(candle["close"])))
            parts.append(f'<path d="M{x:.1f} {y(candle["high"]):.1f}V{y(candle["low"]):.1f}" stroke="{color}" stroke-width="2"/>'
                         f'<rect x="{x-12:.1f}" y="{top:.1f}" width="24" height="{body:.1f}" fill="{color}"/>')
        if item["score"] is not None:
            parts.append(f'<circle cx="{x:.1f}" cy="{y(item["score"]):.1f}" r="4" fill="#e0bd79" stroke="#101114"/>')
        else:
            parts.append(f'<text x="{x:.1f}" y="175" fill="#aaa" text-anchor="middle">待核</text>')
        parts.append(f'<text x="{x:.1f}" y="299" fill="#e3d1ad" text-anchor="middle" font-size="17">{esc(cycle["pillar"])}</text>'
                     f'<text x="{x:.1f}" y="320" fill="#aaa" text-anchor="middle" font-size="11">{cycle["start_year"]}–{cycle["end_year"]}</text>'
                     f'<text x="{x:.1f}" y="338" fill="#aaa" text-anchor="middle" font-size="11">{esc(cycle["note"])}</text></g>')
    return "".join(parts) + "</svg>"


def _paragraph(value):
    return '<p style="white-space:pre-wrap;line-height:1.9">' + esc(value) + '</p>'


def _list(values):
    return '<ul>' + ''.join('<li>' + esc(x) + '</li>' for x in values) + '</ul>'


def citations_html(claim, sources):
    by_id = {s["source_id"]: s for s in sources}
    parts = []
    for reference in claim.get("citations", []):
        source = by_id.get(reference["source_id"], {})
        label = f"《{source.get('book_name', '待核')}》 · {source.get('chapter', '')} · 第 {source.get('line_number', '')} 行"
        parts.append('<blockquote>' + esc(reference["quote"]) + '<br><small>' + esc(label) + '</small></blockquote>')
    return ''.join(parts) if parts else '<small style="opacity:.7">模型推演</small>'


def relations_html(relations, sources):
    output = []
    for relation in relations:
        body = '<details><summary>' + esc(relation.get('label', relation['relation_id'])) + '</summary>'
        body += _paragraph(relation['mechanism'])
        for label, key in (("现实中可能表现", "manifestations"), ("成立条件", "conditions"), ("其他解释与反证", "alternatives")):
            body += '<h4>' + label + '</h4>' + _list(relation[key])
        output.append(body + citations_html(relation, sources) + '</details>')
    return ''.join(output)


def detail_html(item, sources):
    output = [_paragraph(item["assessment"])]
    if "cycle" in item:
        output += [_paragraph('大运综合分：' + score_label(item['score']) + ' · ' + item['rating'])]
        candle = item.get('ohlc')
        output += [_paragraph(f"开 {candle['open']} / 收 {candle['close']} / 高 {candle['high']} / 低 {candle['low']}" if candle else
                              '年度评分有缺项，未绘制完整K线。')]
    for label, key in (("有利之处", "good"), ("不利之处", "bad")):
        output += ['<h4>' + label + '</h4>', _list(item[key])]
    for label, key in (("天干作用", "stem_effect"), ("地支与根气", "branch_effect"), ("格局与喜忌变化", "structure_effect")):
        output += ['<h4>' + label + '</h4>', _paragraph(item[key])]
    for domain in item["domains"]:
        output += ['<h4>' + esc(domain["name"]) + '</h4>', _paragraph(domain["assessment"]), _list(domain["conditions"])]
    output += [citations_html(item, sources), relations_html(item["relation_implications"], sources)]
    if "factors" in item:
        output += ['<h4>综合评分依据</h4>']
        for factor, (_, label, weight) in zip(item["factors"], FACTORS):
            output += [f'<h5>{label} · 权重 {weight}% · {score_label(factor["score"])}</h5>',
                       _paragraph(factor["reason"]), citations_html(factor, sources)]
        output += ['<h4>运内逐年评分（综合分＋年度调整，限制在0–100）</h4>']
        for year in item["years"]:
            output += [f'<details><summary>{year["year"]} {esc(year["pillar"])} · {score_label(year["score"])}</summary>',
                       _paragraph(f'调整分：{year["delta"] if year["delta"] is not None else "待核"}；' + year["reason"]),
                       citations_html(year, sources), '</details>']
    if item["uncertainties"]:
        output += ['<h4>待核条件</h4>', _list(item["uncertainties"])]
    return ''.join(output)


def extended_html(report, sources):
    out = ['<section><h2>关系与现实表现</h2>', relations_html(report.get("relation_implications", []), sources), '</section>']
    if report.get('natal_limitations'):
        out += ['<details><summary>原局分析阶段的局限（岁运已在后续章节补充）</summary>', _list(report['natal_limitations']), '</details>']
    life = report.get("luck_analysis")
    if not life:
        return ''.join(out)
    out += [f'<section><h2>人生 K 线 · {len(life["cycles"])} 步大运</h2>', _paragraph(life['note']), _paragraph(life['scope_note']),
            _paragraph(f"出生后 {life['start_age']} 起运；交运时刻 {life['start']}。"),
            '<div style="overflow-x:auto">' + chart_svg(life) + '</div>',
            _paragraph('每步大运一根K线：开/收为该运首/末流年评分，高/低为全部运内流年评分极值，金点为大运综合分。颜色只反映首末分差，不表示整运好坏；远期排表不表示寿命。')]
    for item in life['cycles']:
        cycle = item['cycle']
        title = f"{cycle['label']} {cycle['pillar']} · {cycle['start_year']}—{cycle['end_year']} · {cycle['note']} · {score_label(item['score'])} · {item['rating']}"
        out += ['<details><summary>' + esc(title) + '</summary>', detail_html(item, sources), '</details>']
    labels = {"annual": "选定流年详解", "monthly": "选定流月详解", "daily": "选定流日详解"}
    for item in life['selected']:
        out += ['<h3>' + labels.get(item['id'], '所选岁运') + '</h3>', _paragraph(json_selected(item['selected'])), detail_html(item, sources)]
    if any(life.get('source_omissions', [])):
        out += [_paragraph('部分生成阶段受上下文预算影响省略了其他古籍段落，《子平真诠》完整保留。各段引用仅使用该次实际发送的来源。')]
    return ''.join(out) + '</section>'


def json_selected(selected):
    return '；'.join(name + '：' + '、'.join(f'{k} {v}' for k, v in data.items()) for name, data in selected.items())


def extended_text(report, sources):
    """Text export uses HTML's text nodes, retaining the same full analysis."""
    from html.parser import HTMLParser
    class Text(HTMLParser):
        def __init__(self):
            super().__init__(); self.parts = []; self.svg_depth = 0
        def handle_starttag(self, tag, attrs):
            if tag == 'svg': self.svg_depth += 1
            if not self.svg_depth and tag in ('p', 'h2', 'h3', 'h4', 'h5', 'summary', 'li', 'blockquote'): self.parts.append('\n')
        def handle_endtag(self, tag):
            if tag == 'svg': self.svg_depth = max(0, self.svg_depth-1)
            if not self.svg_depth and tag in ('p', 'summary', 'li', 'blockquote'): self.parts.append('\n')
        def handle_data(self, data):
            if not self.svg_depth: self.parts.append(data)
    parser = Text(); parser.feed(extended_html(report, sources))
    return ''.join(parser.parts)


def render_extended(report, sources):
    import streamlit as st
    life = report.get('luck_analysis')
    if report.get('relation_implications'):
        st.markdown('### 原局关系与现实表现')
        st.html(relations_html(report['relation_implications'], sources))
    if report.get('natal_limitations'):
        with st.expander('原局分析阶段的局限（岁运见后续章节）'):
            for limitation in report['natal_limitations']:
                st.write(limitation)
    if not life:
        return
    st.markdown(f'### 人生 K 线 · {len(life["cycles"])} 步大运')
    st.caption(SCORE_NOTE)
    st.write(f"出生后 {life['start_age']} 起运 · {life['start']} 交运。")
    st.caption(life['scope_note'])
    st.html('<div style="overflow-x:auto">' + chart_svg(life) + '</div>')
    st.caption('开/收＝首末流年分，高/低＝运内流年分极值，金点＝大运综合分。颜色仅表示首末变化；缺分不补点。')
    for item in life['cycles']:
        cycle = item['cycle']
        with st.expander(f"{cycle['label']} {cycle['pillar']} · {cycle['start_year']}—{cycle['end_year']} · {cycle['note']} · {score_label(item['score'])} · {item['rating']}"):
            st.html(detail_html(item, sources))
    for item in life['selected']:
        st.markdown('### ' + {"annual": "选定流年详解", "monthly": "选定流月详解", "daily": "选定流日详解"}[item['id']])
        st.caption(json_selected(item['selected']))
        st.html(detail_html(item, sources))
    if any(life.get('source_omissions', [])):
        st.caption('部分阶段因窗口预算省略其他古籍段落，《子平真诠》全文保留，引用只按实际提供的段落校验。')
