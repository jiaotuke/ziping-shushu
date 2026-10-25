"""Position-aware 干支 relationships, without silently transforming any pillar.

Engineering references (independent implementation, no upstream code copied):
https://github.com/privilege404/bazi-shaoweihua/blob/main/bazi_shaoweihua/transit.py
https://github.com/jiwenxu025-boop/bazi-engine/blob/main/scripts/bazi_engine/liunian/utils.py
See docs/pillar-relationships.md for the rule conventions and limits.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations

from lunar_python.util import LunarUtil

RULE_VERSION = "positions-and-evidence-3-directed-and-hidden"
NATAL_NAMES = ("年柱", "月柱", "日柱", "时柱")
SCOPE_NAMES = {"natal": "原局", "luck": "大运", "annual": "流年", "monthly": "流月", "daily": "流日"}
SCOPE_LEVELS = {scope: index for index, scope in enumerate(SCOPE_NAMES)}
STEM_ELEMENTS = dict(zip("甲乙丙丁戊己庚辛壬癸", "木木火火土土金金水水"))
CONTROLS = dict(zip("木火土金水", "土金水木火"))
GENERATES = dict(zip("木火土金水", "火土金水木"))
STEM_COMBINATIONS = (("甲己", "土"), ("乙庚", "金"), ("丙辛", "水"), ("丁壬", "木"), ("戊癸", "火"))
BRANCH_COMBINATIONS = (("子丑", "土"), ("寅亥", "木"), ("卯戌", "火"), ("辰酉", "金"), ("巳申", "水"), ("午未", ""))
HARMONIES = (("申子辰", "水"), ("亥卯未", "木"), ("寅午戌", "火"), ("巳酉丑", "金"))
MEETINGS = (("寅卯辰", "木"), ("巳午未", "火"), ("申酉戌", "金"), ("亥子丑", "水"))
STEM_CLASHES = ("甲庚", "乙辛", "丙壬", "丁癸")
BRANCH_CLASHES = ("子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥")
HARMS = ("子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌")
BREAKS = ("子酉", "丑辰", "寅亥", "卯午", "巳申", "未戌")
PUNISHMENT_GROUPS = ("寅巳申", "丑戌未")
PUNISHMENT_DIRECTIONS = ("寅巳", "巳申", "申寅", "丑戌", "戌未", "未丑", "子卯", "卯子")
# Rule data follows china-testing/bazi ganzhi.py zhi_atts['暗']; no upstream implementation copied.
HIDDEN_COMBINATIONS = ("寅丑", "卯申", "午亥")
RULE_SOURCE = "https://github.com/china-testing/bazi/blob/master/ganzhi.py"
TRANSFORM_TYPES = {"stem_combination", "branch_combination", "three_harmony", "three_meeting"}
DISRUPTION_TYPES = {"stem_clash", "branch_clash", "punishment_pair", "self_punishment", "harm", "break"}


def _node(key: str, name: str, pillar: str, scope: str, order: int) -> dict:
    if not isinstance(pillar, str) or pillar not in LunarUtil.JIA_ZI:
        raise ValueError(f"{name}不是有效的六十甲子干支。")
    return {"id": key, "name": name, "pillar": pillar, "stem": pillar[0],
            "branch": pillar[1], "scope": scope, "order": order}


def _event(kind: str, label: str, members: tuple, *, element: str = "", note: str = "", group: str = "", directions=()) -> dict:
    identifiers = ":".join(n["id"] for n in members)
    scopes = {n["scope"] for n in members}
    scope = max(scopes, key=SCOPE_LEVELS.__getitem__)
    return {"id": f"{kind}:{identifiers}", "kind": kind, "label": label,
            "scope": scope, "members": list(members), "element": element,
            "note": note, "group": group,
            **({"directions": [{"from": a["id"], "to": b["id"]} for a, b in directions]} if directions else {})}


def _matches(a: str, b: str, rules) -> str | None:
    return next((pair for pair in rules if frozenset(pair) == frozenset((a, b))), None)


def _pair_events(left: dict, right: dict) -> list[dict]:
    members = (left, right)
    stems = frozenset((left["stem"], right["stem"]))
    branches = frozenset((left["branch"], right["branch"]))
    events = []
    for source, target in ((left, right), (right, left)):
        a, b = STEM_ELEMENTS[source["stem"]], STEM_ELEMENTS[target["stem"]]
        for kind, table, verb in (("stem_generate", GENERATES, "生"), ("stem_control", CONTROLS, "克")):
            if table[a] == b:
                events.append(_event(kind, source["stem"]+verb+target["stem"], members,
                    directions=((source, target),), note="按天干五行记录施受方向，不代表作用已落实、力量大小或必然吉凶；与合冲并列保留。"))
    for pair, element in STEM_COMBINATIONS:
        if stems == frozenset(pair):
            events.append(_event("stem_combination", pair + "合", members, element=element,
                                 note=f"五合配对命中；化{element}条件须另核。"))
    if pair := _matches(left["stem"], right["stem"], STEM_CLASHES):
        events.append(_event("stem_clash", pair + "冲", members,
                             note="采用甲庚、乙辛、丙壬、丁癸四组天干冲口径。"))
    for pair, element in BRANCH_COMBINATIONS:
        if branches == frozenset(pair):
            note = f"六合配对命中；化{element}条件须另核。" if element else "午未六合；化土、化火存在不同口径，本项目不预定化神。"
            events.append(_event("branch_combination", pair + "合", members, element=element, note=note))
    for kind, suffix, table in (("branch_clash", "冲", BRANCH_CLASHES), ("harm", "害", HARMS), ("break", "破", BREAKS)):
        if pair := _matches(left["branch"], right["branch"], table):
            events.append(_event(kind, pair + suffix, members))
    directions = tuple((a, b) for a, b in ((left, right), (right, left))
                       if a["branch"]+b["branch"] in PUNISHMENT_DIRECTIONS)
    if branches == frozenset("子卯"):
        events.append(_event("punishment_pair", "子卯互刑", members, directions=directions,
                             note="子刑卯、卯刑子分别保留方向；配对不等于具体灾事。"))
    for group in PUNISHMENT_GROUPS:
        if len(branches) == 2 and branches <= set(group):
            source, target = directions[0]
            label = source["branch"]+"刑"+target["branch"]
            events.append(_event("punishment_pair", label + "（两支）", members, group=group, directions=directions,
                                 note="标记三刑组内的两支相刑；完整三刑另列，不以此删除其他刑。"))
    if left["branch"] == right["branch"] and left["branch"] in "辰午酉亥":
        events.append(_event("self_punishment", left["branch"] * 2 + "自刑", members, directions=((left,right),(right,left)),
                             note="必须是两个不同柱位出现相同支；单独一支不计自刑。"))
    for group, element in HARMONIES:
        if len(branches) != 2 or not branches <= set(group):
            continue
        pair = "".join(branch for branch in group if branch in branches)
        if group[1] in branches:
            events.append(_event("half_harmony", pair + "半合", members, element=element, group=group,
                                 note="采用含中神的生旺、旺墓半合口径；不按固定比例折算力量。"))
        else:
            events.append(_event("arched_harmony", pair + "拱合配对", members, element=element, group=group,
                                 note=f"两端支配对，中神为{group[1]}；不作为标准半合或完整三合。"))
    for group, element in MEETINGS:
        if len(branches) == 2 and branches <= set(group):
            pair = "".join(branch for branch in group if branch in branches)
            arched = group[1] not in branches
            missing = "".join(branch for branch in group if branch not in branches)
            events.append(_event("half_meeting", pair + ("半会（拱会）" if arched else "半会"), members,
                element=element, group=group,
                note=f"采用china-testing/bazi的会方两支配对口径；缺{missing}，只作未齐候选，不按完整三会或固定比例折算力量。"))
    if pair := _matches(left["branch"], right["branch"], HIDDEN_COMBINATIONS):
        hidden_pairs = [a+b for a in LunarUtil.ZHI_HIDE_GAN[left["branch"]] for b in LunarUtil.ZHI_HIDE_GAN[right["branch"]]
                        if any(frozenset(a+b) == frozenset(p) for p, _ in STEM_COMBINATIONS)]
        events.append(_event("hidden_combination", pair+"暗合配对", members,
            note="采用china-testing/bazi的寅丑、卯申、午亥口径；藏干五合线索："+"、".join(hidden_pairs)
                 +"。仅作候选，不等同六合或成化，不直接指认婚恋、隐情等现实事件。"))
    return events


def _group_events(nodes: list[dict]) -> list[dict]:
    events = []
    for members in combinations(nodes, 3):
        branches = {n["branch"] for n in members}
        for kind, suffix, groups in (("three_harmony", "三合", HARMONIES), ("three_meeting", "三会", MEETINGS)):
            for group, element in groups:
                if branches == set(group):
                    events.append(_event(kind, group + suffix, members, element=element, group=group,
                                         note=f"三支配齐，{element}为候选五行；是否成局、成化仍须核对。"))
        for group in PUNISHMENT_GROUPS:
            if branches == set(group):
                events.append(_event("three_punishments", group + "三刑", members, group=group,
                                     note="三支配齐；两支刑的柱位记录仍保留。"))
    return events


def _stage_note(event: dict, nodes: list[dict]) -> str:
    if event["scope"] == "natal":
        return "原局已有"
    scope = event["scope"]
    name = SCOPE_NAMES[scope]
    if event["kind"] not in {"three_harmony", "three_meeting", "three_punishments"}:
        return name + "新增配对"
    required = set(event["group"])
    for earlier, level in SCOPE_LEVELS.items():
        if level >= SCOPE_LEVELS[scope]:
            break
        branches = {n["branch"] for n in nodes if SCOPE_LEVELS[n["scope"]] <= level}
        if required <= branches:
            prefix = "原局支组已齐" if earlier == "natal" else SCOPE_NAMES[earlier] + "阶段已齐"
            return prefix + "，" + name + "新增参与位置"
    return name + "补齐组合"


def _position_evidence(event: dict, nodes: list[dict]) -> dict:
    members = event["members"]
    if event["scope"] != "natal":
        return {"label": "位置", "text": "涉及运年、流月或流日：不套用原局四柱的相邻顺序；作用先后与远近待核。", "status": "review"}
    if len(members) != 2:
        return {"label": "位置", "text": "三支分别位于" + "、".join(n["name"] for n in members) + "；配齐不等于成化。", "status": "observed"}
    left, right = members
    between = [n for n in nodes if n["scope"] == "natal" and left["order"] < n["order"] < right["order"]]
    text = "原局两柱相邻。" if not between else "原局隔位，中间为" + "、".join(n["name"] + n["pillar"] for n in between) + "。"
    if event["kind"] == "stem_combination":
        blockers = [n["name"] + n["stem"] + "克" + m["stem"] for n in between for m in members
                    if CONTROLS[STEM_ELEMENTS[n["stem"]]] == STEM_ELEMENTS[m["stem"]]]
        if blockers:
            text += "间隔天干存在克制线索：" + "、".join(blockers) + "；须核对是否阻合。"
    return {"label": "位置", "text": text, "status": "observed"}


def _transformation_review(event: dict, nodes: list[dict], events: list[dict]) -> dict:
    """List observations and unanswered conditions; no observation is a 化气 verdict."""
    element = event["element"]
    members = event["members"]
    member_ids = {n["id"] for n in members}
    # The natal month stays the month authority at every transit stage.
    month = next(n for n in nodes if n["id"] == "natal_1")
    main_hidden = LunarUtil.ZHI_HIDE_GAN[month["branch"]][0]
    checks = [{"label": "原局月令", "status": "observed",
               "text": f"{month['pillar']}，月支{month['branch']}，本气{main_hidden}{STEM_ELEMENTS[main_hidden]}；是否得令须结合化神与季节，不因岁运更换月令。"}]
    selected_month = next((n for n in nodes if n["scope"] == "monthly"), None)
    if selected_month:
        checks.append({"label": "所选流月", "status": "observed",
                       "text": f"{selected_month['name']} {selected_month['pillar']}，仅作当前节月的时令线索；不替代出生月令，是否影响本合须另核。"})
    if element:
        # Only a heavenly-stem combination already uses those stems as operands.
        # For a branch combination, its own pillar's stem CAN be visible support.
        excluded_stems = member_ids if event["kind"] == "stem_combination" else set()
        visible = [n["name"] + n["stem"] for n in nodes if n["id"] not in excluded_stems and STEM_ELEMENTS[n["stem"]] == element]
        hidden = [n["name"] + n["branch"] + "藏" + "、".join(h for h in LunarUtil.ZHI_HIDE_GAN[n["branch"]] if STEM_ELEMENTS[h] == element)
                  for n in nodes if any(STEM_ELEMENTS[h] == element for h in LunarUtil.ZHI_HIDE_GAN[n["branch"]])]
        checks.extend([
            {"label": "其他透干" if excluded_stems else "透干线索", "status": "observed" if visible else "review",
             "text": ("同候选五行的透干：" + "、".join(visible) if visible else f"当前审核范围未见可列为额外支持的{element}透干") + "；不据此单独判化。"},
            {"label": "藏干线索", "status": "observed" if hidden else "review",
             "text": ("同候选五行的藏干：" + "；".join(hidden) if hidden else f"当前范围未见{element}藏干") + "；藏干出现不等于根气有力。"},
        ])
    else:
        checks.append({"label": "化神口径", "status": "review", "text": "午未合火、合土存在不同取法；未统一化神，暂不作同类五行支持判断。"})
    checks.append(_position_evidence(event, nodes))
    if event["kind"] == "stem_combination":
        counts = Counter(n["stem"] for n in nodes)
        extra = [n["name"] + n["stem"] for n in nodes if n["id"] not in member_ids and any(n["stem"] == m["stem"] for m in members)]
        checks.append({"label": "多重配对", "status": "review" if extra else "observed",
                       "text": ("同一合组另见" + "、".join(extra) + "；存在多对一配对线索，争合须结合隔位判断。")
                       if any(counts[m["stem"]] > 1 for m in members) else "当前范围未见本五合组同干重复；不据此确认合化。"})
    related = [r for r in events if r["id"] != event["id"] and r["kind"] in DISRUPTION_TYPES
               and member_ids.intersection(n["id"] for n in r["members"])]
    checks.append({"label": "相关冲刑害破", "status": "review" if related else "observed",
                   "text": ("相关柱另见" + "；".join(r["label"] + "（" + "、".join(n["name"] for n in r["members"]) + "）" for r in related)
                            + "；是否影响本合、能否解冲须分别判断。") if related else "当前范围未命中相关柱的冲刑害破；不能据此认定无其他阻碍。"})
    checks.append({"label": "尚待核定", "status": "review",
                   "text": "化神旺衰、原有根气是否保留、合绊与成化、格局喜忌及救应尚未完成判断；不改写干支与十神。"})
    return {"id": event["id"], "label": event["label"], "members": members,
            "scope": event["scope"], "element": element, "status": "合化待核",
            "checks": checks, "source_chapters": ["论十干合而不合", "论刑冲会合解法"]}


def analyze_relationships(pillars: dict, *, luck_pillar: str | None = None, annual_pillar: str | None = None,
                          monthly_pillar: str | None = None, daily_pillar: str | None = None,
                          luck_label: str = "大运", annual_label: str = "流年",
                          monthly_label: str = "流月", daily_label: str = "流日") -> dict:
    """All relationships have exact pillar identities, stage and rule evidence.

    Each review uses only its own scope and coarser scopes: natal, luck, year,
    month, day. A daily clash never leaks backward into the natal/year audit.
    The pre-luck blank pillar is omitted, never replaced by a fabricated pillar.
    """
    if set(pillars) != set(NATAL_NAMES):
        raise ValueError("干支关系计算需要完整的年、月、日、时四柱。")
    nodes = [_node(f"natal_{i}", "原局" + name, pillars[name], "natal", i) for i, name in enumerate(NATAL_NAMES)]
    if luck_pillar:
        nodes.append(_node("luck", luck_label, luck_pillar, "luck", 4))
    if annual_pillar:
        nodes.append(_node("annual", annual_label, annual_pillar, "annual", 5))
    if monthly_pillar:
        nodes.append(_node("monthly", monthly_label, monthly_pillar, "monthly", 6))
    if daily_pillar:
        nodes.append(_node("daily", daily_label, daily_pillar, "daily", 7))
    events = [event for pair in combinations(nodes, 2) for event in _pair_events(*pair)] + _group_events(nodes)
    scopes = SCOPE_LEVELS
    for event in events:
        event["stage_note"] = _stage_note(event, nodes)
        active = [n for n in nodes if scopes[n["scope"]] <= scopes[event["scope"]]]
        if event["kind"] in {"half_harmony", "arched_harmony", "half_meeting"} and set(event["group"]) <= {n["branch"] for n in active}:
            event["note"] += " 当前范围该组三支已齐，完整组合另列；两支与三支记录不累加折算力量。"
    # Review each relation against its own scope; later transit evidence is separate.
    reviews = []
    for event in events:
        if event["kind"] not in TRANSFORM_TYPES:
            continue
        level = scopes[event["scope"]]
        active = [n for n in nodes if scopes[n["scope"]] <= level]
        active_events = [r for r in events if scopes[r["scope"]] <= level]
        reviews.append(_transformation_review(event, active, active_events))
    # Transit support or disruption can affect an existing combination. Keep its
    # original review intact and always add a separate current-stage review.
    current_scope = max((n["scope"] for n in nodes), key=scopes.__getitem__)
    if current_scope != "natal":
        for event in events:
            if event["kind"] not in TRANSFORM_TYPES or event["scope"] == current_scope:
                continue
            review = _transformation_review(event, nodes, events)
            review.update({"id": event["id"] + ":current", "scope": current_scope,
                           "label": event["label"] + " · 当前运程复核"})
            reviews.append(review)
    return {"version": RULE_VERSION, "nodes": nodes,
            "groups": [{"id": scope, "label": label, "events": [r for r in events if r["scope"] == scope]}
                       for scope, label in (("natal", "原局关系"), ("luck", "大运引动"), ("annual", "流年引动"),
                                            ("monthly", "流月引动"), ("daily", "流日引动"))],
            "reviews": reviews,
            "summary": "保留全部参与柱位；合、冲等关系并列，不自动互相抵消。组合命中不等于成局、成化或具体事件。"}


def relationship_facts(analysis: dict) -> dict:
    """Compact facts for the model; repeated UI review prose need not consume context."""
    return {
        "规则版本": analysis["version"],
        "柱位": [{"id": n["id"], "名称": n["name"], "干支": n["pillar"], "范围": n["scope"]} for n in analysis["nodes"]],
        "关系": [{"id": r["id"], "类型": r["kind"], "关系": r["label"], "范围": r["scope"],
                  "参与位置": [n["id"] for n in r["members"]], "标记": r["stage_note"],
                  **({"作用方向": [{"施方": d["from"], "受方": d["to"]} for d in r["directions"]]} if r.get("directions") else {}),
                  **({"候选五行": r["element"], "合化结论": "未判定"} if r["kind"] in TRANSFORM_TYPES else {}),
                  **({"候选五行": r["element"], "组合结论": "未判定", "规则来源": RULE_SOURCE,
                      "规则说明": r["note"]} if r["kind"] in {"half_meeting", "hidden_combination"} else {}),
                  **({"所属支组": r["group"]} if r["group"] else {})}
                 for group in analysis["groups"] for r in group["events"]],
        "使用约束": [analysis["summary"], "原局月令不被大运、流年、流月、流日替换；流月只提供当前节月线索。",
                     "半合须含中神；拱合、半合、完整三合不累加折算力量。午未六合未统一化神。",
                     "半会/拱会与暗合仅为所选口径的候选配对，不按完整合会判定；暗合不直接对应婚外情或其他具体事件。",
                     "天干生克与刑须按作用方向读取，存在关系不等于实际生克制化成立，不按条数累加吉凶。",
                     "得令、根气与透干、旺衰、隔位及争合、合冲解救均须结合原文复核；不得见合即化或改写干支十神。"],
    }
