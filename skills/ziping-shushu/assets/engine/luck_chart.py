"""Code-drawn, offline SVG chart and escaped views shared by reports and Android."""

from __future__ import annotations

import html

from luck_analysis import FACTORS, SCORE_NOTE

DASHBOARD_UI_VERSION = "v5_years_2"


def esc(value):
    return html.escape(str(value), quote=True)


def score_label(value):
    return "证据不足，暂不评分" if value is None else f"{value:g} / 100"


def chart_svg(life, *, interactive=False):
    cycles = life["cycles"]
    width, height = max(920, len(cycles) * 86 + 80), 350
    y = lambda score: 35 + (100 - score) * 2.4
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="子平K线，项目解释性评分" viewBox="0 0 {width} {height}" style="width:100%;min-width:850px;font-family:serif;background:#101114;color:#ddd">',
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
        attributes = f' data-cycle-index="{i}" role="button" tabindex="0" aria-label="{esc(title)}" aria-pressed="false"' if interactive else ''
        parts.append(f'<g{attributes}><title>{esc(title)}</title>')
        if interactive:
            hit_width = (width - 115) / max(len(cycles), 1)
            parts.append(f'<rect class="candle-hit" x="{x-hit_width/2:.1f}" y="20" width="{hit_width:.1f}" height="326" rx="10" fill="transparent"/>')
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


def dashboard_payload(report):
    from report_presentation import presentation_view
    life = report.get("luck_analysis")
    cycles = []
    for item in life.get("cycles", []) if life else []:
        cycle = item["cycle"]
        cycles.append({"id": cycle["id"], "title": cycle["label"] + " · " + cycle["pillar"],
                       "range": f"{cycle['start_year']}—{cycle['end_year']} · {cycle['note']}",
                       "score": score_label(item["score"]), "rating": item["rating"],
                       "start_year": cycle["start_year"], "end_year": cycle["end_year"],
                       "ohlc": item.get("ohlc"), "detail": cycle_detail_view(item), **presentation_view(item)})
    labels = {"annual": "流年重点", "monthly": "流月重点", "daily": "流日重点"}
    periods = []
    initial = 0
    for item in life.get("selected", []) if life else []:
        periods.append({"title": labels.get(item["id"], "所选时间"), "range": json_selected(item["selected"]),
                        **presentation_view(item)})
        if item["id"] == "annual":
            year = item["selected"].get("流年", {}).get("年份")
            initial = next((i for i, c in enumerate(cycles) if type(year) is int and c["start_year"] <= year <= c["end_year"]), 0)
    return {"chart": chart_svg(life, interactive=True) if life and cycles else "", "cycles": cycles,
            "initial_index": initial, "natal": presentation_view(report), "periods": periods,
            "score_note": SCORE_NOTE,
            "scope_note": life["scope_note"] if life else "仅原局解读，未生成岁运评分或K线。"}


def cycle_detail_view(item):
    """Expose already-generated explanations and annual scores without another model request."""
    return {"assessment": item.get("assessment", ""), "good": item.get("good", []), "bad": item.get("bad", []),
            "effects": [{"label": label, "text": item.get(key, "")} for key, label in
                        (("stem_effect", "天干作用"), ("branch_effect", "地支与根气"), ("structure_effect", "格局与喜忌变化"))],
            "domains": item.get("domains", []), "uncertainties": item.get("uncertainties", []),
            "factors": [{"label": label, "weight": weight, "score": score_label(factor.get("score")), "reason": factor.get("reason", "")}
                        for factor, (_, label, weight) in zip(item.get("factors", []), FACTORS)],
            "years": [{"year": year["year"], "pillar": year.get("pillar", ""), "score": year.get("score"),
                       "score_label": score_label(year.get("score")), "delta": year.get("delta"), "reason": year.get("reason", "")}
                      for year in item.get("years", [])]}


def cycle_detail_html(item):
    """Same selected-cycle section in full text/print overviews."""
    out = ['<section><h3>这步大运怎么理解</h3>', _paragraph(item.get('assessment', ''))]
    for key, label in (("good", "有利之处"), ("bad", "值得留意")):
        out += ['<h4>' + label + '</h4>', _list(item.get(key, []))]
    out += ['<h3>运内逐年评分与解读</h3>']
    for year in item.get('years', []):
        out += ['<details><summary>' + esc(f"{year['year']} {year.get('pillar', '')} · {score_label(year.get('score'))}") + '</summary>',
                _paragraph(year.get('reason', '')),
                _paragraph('相对大运基线的调整：' + (f"{year['delta']:+g}" if year.get('delta') is not None else '待核')), '</details>']
    return ''.join(out) + '</section>'


def dashboard_document(report):
    """Self-contained interactive HTML; JSON cannot escape its inert script element."""
    import json
    from runtime_paths import RESOURCE_ROOT
    template = (RESOURCE_ROOT / "components/life_report/index.html").read_text(encoding="utf-8")
    data = json.dumps(dashboard_payload(report), ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return template.replace('<script id="ziping-initial-data" type="application/json"></script>',
                            '<script id="ziping-initial-data" type="application/json">' + data + '</script>')


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


def summary_html(document, title):
    from report_presentation import presentation_view
    view = presentation_view(document)
    out = ['<section class="result-summary"><h3>' + esc(title) + '</h3>', _paragraph(view["overview"]["headline"])]
    if "score" in document:
        out.append(_paragraph('命理解读参考分：' + score_label(document['score']) + ' · ' + document['rating']))
    for key, label in (("opportunity", "可以把握"), ("caution", "值得留意")):
        if view["overview"][key]:
            out.append(_paragraph(label + '：' + view["overview"][key]))
    out.append('<div class="summary-cards">')
    for card in view["cards"]:
        out += ['<article><h4>' + esc(card['label']) + '</h4>', _paragraph(card['summary'])]
        if card['advice']:
            out.append(_paragraph('建议：' + card['advice']))
        if card['legacy']:
            out.append(_paragraph(card['note']))
        out.append('</article>')
    return ''.join(out) + '</div></section>'


def results_html(report):
    """Static full overview, also used for complete text/print exports."""
    life = report.get('luck_analysis')
    if not life:
        return summary_html(report, '原局概览')
    out = ['<section><h2>子平 K 线</h2>', _paragraph(SCORE_NOTE), _paragraph(life['scope_note']),
           '<div style="overflow-x:auto">' + chart_svg(life) + '</div>']
    for item in life['cycles']:
        c = item['cycle']
        out.append(summary_html(item, f"{c['label']} {c['pillar']} · {c['start_year']}—{c['end_year']} · {c['note']}"))
        out.append(cycle_detail_html(item))
    for item in life['selected']:
        out += [summary_html(item, {"annual": "流年重点", "monthly": "流月重点", "daily": "流日重点"}.get(item['id'], '所选时间')),
                _paragraph(json_selected(item['selected']))]
    return ''.join(out) + '</section>'


def reasoning_html(report, sources):
    from ai_analysis import STEP_TITLES
    out = ['<section><h2>原局判断与推导依据</h2>', _paragraph(report['summary'])]
    for step in report['steps']:
        out += ['<details><summary>' + esc(f"{step['step']}. {STEP_TITLES[step['step']-1]}") + '</summary>',
                _paragraph(step['conclusion']), _list(step.get('chart_evidence', [])), citations_html(step, sources),
                _list(step.get('uncertainties', [])), '</details>']
    out += ['<h3>原局关系与现实表现</h3>', relations_html(report.get('relation_implications', []), sources)]
    life = report.get('luck_analysis')
    if life:
        out += ['<h2>逐运推导与评分依据</h2>']
        for item in life['cycles']:
            c = item['cycle']
            title = f"{c['label']} {c['pillar']} · {c['start_year']}—{c['end_year']}"
            out += ['<details><summary>' + esc(title) + '</summary>', detail_html(item, sources), '</details>']
        for item in life['selected']:
            title = {"annual": "所选流年推导", "monthly": "所选流月推导", "daily": "所选流日推导"}.get(item['id'], '所选时间推导')
            out += ['<details><summary>' + title + '</summary>', _paragraph(json_selected(item['selected'])), detail_html(item, sources), '</details>']
        if any(life.get('source_omissions', [])):
            out.append(_paragraph('部分阶段因窗口预算省略其他古籍段落，《子平真诠》全文保留；引用仅按实际提供的段落核对。'))
    out += ['<h3>待核条件与局限</h3>', _list(report.get('natal_limitations', [])), _list(report.get('limitations', []))]
    return ''.join(out) + '</section>'


def extended_html(report, sources):
    return results_html(report) + '<details><summary>查看完整推导与古籍依据</summary>' + reasoning_html(report, sources) + '</details>'


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


def render_extended(report, sources, *, key='life_report'):
    from pathlib import Path
    import streamlit as st
    import streamlit.components.v1 as components
    # Reload the changed frontend without discarding the report or model checkpoints.
    dashboard = components.declare_component('ziping_life_report_' + DASHBOARD_UI_VERSION, path=str(Path(__file__).parent / 'components/life_report'))
    dashboard(payload=dashboard_payload(report), key=key + '_' + DASHBOARD_UI_VERSION, default=None)
    with st.expander('查看完整推导与古籍依据', expanded=False):
        st.html(reasoning_html(report, sources))
        st.caption('原文摘录已核对；没有引用的内容为模型推演。摘录对应原文不代表解释适用性已获确认。')
