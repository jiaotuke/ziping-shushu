"""Local, relationship-conditioned retrieval for Qian Li Ming Gao.

Chapter selection and literal pair ranking are retrieval clues, never a verdict
that the author's conditions or historical outcomes apply to this chart.
"""
from __future__ import annotations

from collections import deque
import hashlib
import re

BOOK = "千里命稿"
RETRIEVAL_VERSION = "qianli-relations-and-year-trace-1"
SECTIONS = {
    "stem_generate": ("五行篇", "人元篇"),
    "stem_control": ("干克", "干克之影响", "干克之区别", "干克干合并见"),
    "stem_combination": ("干合", "干合之影响", "干合之区别", "干合而化", "干克干合并见"),
    "stem_clash": ("干克", "干克之影响", "干克之区别"),
    "branch_combination": ("支合种类", "支合之影响", "支合之区别"),
    "three_harmony": ("支合种类", "支合之影响", "支合之区别"),
    "three_meeting": ("支合种类", "支合之影响", "支合之区别"),
    "half_harmony": ("支合种类", "支合之影响", "支合之区别"),
    "arched_harmony": ("支合种类", "支合之影响", "支合之区别"),
    "branch_clash": ("支冲", "支冲之影响", "支冲之区别"),
    "punishment_pair": ("支刑", "支刑之影响"),
    "three_punishments": ("支刑", "支刑之影响"),
    "self_punishment": ("支刑", "支刑之影响"),
    "harm": ("支害", "支害之影响"),
}


def load_records(path):
    """Use this transcription's TOC, exclude TOC hits, retain original lines."""
    from source_data import make_source_id
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i,line in enumerate(lines) if line.strip() == "杨叔和序"]
    if len(starts) != 2:
        raise ValueError("《千里命稿》目录与正文起点不符，请核对当前电子底本。")
    first = starts[1]
    titles = {line.strip() for line in lines[starts[0]:first] if line.strip()}
    citation = "；".join(line[1:].strip() for line in lines if line.startswith('#'))
    records, paragraph = [], []
    parent, heading = "", ""
    def flush():
        if not paragraph:
            return
        text = '\n'.join(line for _,line in paragraph).strip()
        aliases = [make_source_id(path.name,n,line) for n,line in paragraph]
        records.append(dict(source_id=aliases[0],source_aliases=aliases,source_file=path.name,
                            book_name=BOOK,citation=citation,section=parent+" / "+heading,
                            line_number=paragraph[0][0],end_line_number=paragraph[-1][0],text=text))
        paragraph.clear()
    for n,raw in enumerate(lines[first:],first+1):
        text = raw.strip()
        if not text:
            flush()
            continue
        short_heading = text in titles or bool(re.fullmatch(r"[干支][克合冲刑害](?:种类|之影响|之区别)",text))
        if len(text) == 1:
            short_heading = ((parent == "天干篇" and text in "甲乙丙丁戊己庚辛壬癸")
                             or (parent == "地支篇" and text in "子丑寅卯辰巳午未申酉戌亥")
                             or (parent == "五行篇" and text in "金木水火土")
                             or parent in ("富贵吉寿篇","贫贱凶夭篇") and text in titles)
        if short_heading:
            flush()
            if text.endswith(("篇","序")):
                parent,heading = text,text
            else:
                heading = text
            continue
        if paragraph and re.search(r"[。！？!?；]$",paragraph[-1][1]):
            flush()
        paragraph.append((n,text))
    flush()
    return records


def _rank(records, relation):
    kind = relation['类型']
    wanted = SECTIONS.get(kind, ())
    # No silent equivalence: a 三合 called 半会 in a historical example is
    # not evidence for our 三会方 half_meeting; 暗合格 is not the three pairs.
    if not wanted:
        return []
    label = relation['关系']
    glyphs = re.findall(r'[甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥]',label)
    unique = list(dict.fromkeys(glyphs))
    ranked = []
    for record in records:
        section = str(record['section'])
        leaf = section.rsplit(' / ',1)[-1]
        if not (leaf in wanted or any(term.endswith('篇') and section.startswith(term+' / ') for term in wanted)):
            continue
        text = str(record['text'])
        if len(text) < 20:
            continue
        pair = len(unique) >= 2 and all(glyph in text for glyph in unique)
        exact = label in text
        score = 20*exact + 5*pair + sum(min(text.count(glyph),3) for glyph in unique)
        ranked.append((score,int(record['line_number']),record,'字面配对线索' if pair else '关系通则参考'))
    ranked.sort(key=lambda item:(-item[0],item[1]))
    return ranked


def select_relationships(requests, *, max_characters=10000):
    """Round-robin periods/relations so an early year cannot consume the budget."""
    from source_data import load_source_records
    records = load_source_records(BOOK)
    if not records:
        return [], [{"period": period, "relations": [], "corpus_unavailable": True} for period, _ in requests]
    queues, trace = [], []
    for period,relations in requests:
        period_trace = {'period':period,'relations':[]}
        period_queue = deque()
        for relation in relations:
            candidates = _rank(records,relation)
            row = {'relation_id':relation['id'],'relation':relation['关系'],'source_ids':[],
                   'candidate_count':len(candidates),
                   'status':'待选取' if candidates else '未找到可直接定位的关系篇章'}
            period_trace['relations'].append(row)
            if candidates:
                period_queue.append(deque((hit,row) for hit in candidates[:2]))
        queues.append(period_queue)
        trace.append(period_trace)
    selected,used = {},0
    while any(queues):
        for period_queue in queues:
            if not period_queue:
                continue
            queue = period_queue.popleft()
            (_,_,record,match),row = queue.popleft()
            if queue:
                period_queue.append(queue)
            sid = record['source_id']
            if sid not in selected and used+len(record['text']) > max_characters:
                row['status'] = '受上下文预算限制，未全部提供'
                continue
            if sid not in selected:
                selected[sid] = {**record,'retrieval_match':match}
                used += len(record['text'])
            if sid not in row['source_ids']:
                row['source_ids'].append(sid)
            row['status'] = '已检索候选；适用性未核定'
    return list(selected.values()),trace


def retrieve(chart, topic, count, collection):
    from pillar_relationships import analyze_relationships,relationship_facts
    facts = relationship_facts(analyze_relationships(chart['四柱']))
    records,trace = select_relationships([('原局',facts['关系'])],max_characters=8000)
    return {'results':[{'document':r['text'],'distance':0,'metadata':{
                'book_name':BOOK,'source_id':r['source_id'],'source_ids':[r['source_id']],
                'chapter':r['section'],'line_number':f"{r['line_number']}-{r['end_line_number']}",
                'citation':r['citation'],'retrieval_method':'原局干支关系定位',
                'retrieval_query':'、'.join(row['relation'] for p in trace for row in p['relations'] if r['source_id'] in row['source_ids'])
                    +'；'+r['retrieval_match']+'；仅为相关原文候选'}} for r in records],
            'mode':'relationship_conditioned','chapter':None,'annotation_issues':[], 'trace':trace}


def corpus_signature():
    """Content identity survives copying the same source to the preview folder."""
    from source_data import load_source_records
    records = load_source_records(BOOK)
    return hashlib.sha256('\n'.join(r['source_id']+':'+r['section'] for r in records).encode()).hexdigest()


def stage_context(context,focus):
    """Replace natal excerpts with independently retrieved current-stage excerpts."""
    requests = [(focus['id'],[r for r in focus['relations']['关系'] if r['范围'] == focus['level']])]
    if focus['level'] == 'luck':
        requests += [(str(year['id']),year['annual_relations']) for year in focus['cycle']['years']]
    else:
        order = ('luck','annual','monthly','daily')
        requests += [('背景:'+scope,[r for r in focus['relations']['关系'] if r['范围']==scope])
                     for scope in reversed(order[:order.index(focus['level'])])]
    records,trace = select_relationships(requests)
    sources = [s for s in context['sources'] if s['book_name'] != BOOK]
    for r in records:
        sources.append({'source_id':'Q'+r['source_id'][:20],'original_source_id':r['source_id'],
                        'book_name':BOOK,'chapter':r['section'],
                        'line_number':f"{r['line_number']}-{r['end_line_number']}",'text':r['text']})
    remap = {s['original_source_id']:s['source_id'] for s in sources if s['book_name'] == BOOK}
    for period in trace:
        for row in period['relations']:
            row['source_ids'] = [remap[sid] for sid in row['source_ids'] if sid in remap]
    return {**context,'sources':sources,'qianli_retrieval':{'version':RETRIEVAL_VERSION,'periods':trace,
             'note':'按当前阶段及运内各年引动关系独立检索；同段去重，通则/字面命中不代表条件成立。'} }


def trace_for_sources(context):
    trace = context.get('qianli_retrieval',{})
    available = {s['source_id'] for s in context['sources']}
    return {'version':trace.get('version',RETRIEVAL_VERSION),'note':trace.get('note',''),
            'periods':[{'period':p['period'],
                'source_ids':sorted({sid for row in p['relations'] for sid in row['source_ids'] if sid in available}),
                'unmatched_relations':[row['relation_id'] for row in p['relations'] if not row['candidate_count']],
                'budget_omitted_relations':[row['relation_id'] for row in p['relations']
                    if row['candidate_count'] and not any(sid in available for sid in row['source_ids'])]}
                for p in trace.get('periods',[])]}
