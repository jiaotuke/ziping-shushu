"""《三命通会》明确取法的常见命局神煞（仅标记出现位置，不作吉凶断语）。"""

from __future__ import annotations

BRANCHES = "子丑寅卯辰巳午未申酉戌亥"

# 依据《三命通会》卷三“论十干禄”：戊寄巳、己寄午。
LU_BRANCH = {
    "甲": "寅", "乙": "卯", "丙": "巳", "丁": "午", "戊": "巳",
    "己": "午", "庚": "申", "辛": "酉", "壬": "亥", "癸": "子",
}

# 采用卷三“论天乙贵人”开篇所载歌诀；原文还收录其他推法，暂不混用。
TIANYI_BRANCHES = {
    "甲": "丑未", "戊": "丑未", "庚": "丑未",
    "乙": "子申", "己": "子申", "丙": "亥酉", "丁": "亥酉",
    "壬": "卯巳", "癸": "卯巳", "辛": "寅午",
}

# 采用卷三“论羊刃”明确提到的子平取法：五阳干有刃，五阴干不取羊刃。
YANGREN_BRANCH = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子"}

# 《三命通会》卷二“论将星华盖”“论咸池”及卷三相关篇目，按年支三合局起神煞。
# 生人基准采用年支；命局四支中出现目标支时，记录对应柱位。
TRIAD_STARS = {
    "申子辰": {
        "驿马": ("寅", "卷三·论驿马"),
        "劫煞": ("巳", "卷三·论劫煞亡神"),
        "亡神": ("亥", "卷三·论劫煞亡神"),
        "灾煞": ("午", "卷三·论灾煞"),
        "六厄": ("卯", "卷三·论六厄"),
        "桃花（咸池）": ("酉", "卷二·论咸池"),
        "将星": ("子", "卷二·论将星华盖"),
        "华盖": ("辰", "卷二·论将星华盖"),
    },
    "寅午戌": {
        "驿马": ("申", "卷三·论驿马"),
        "劫煞": ("亥", "卷三·论劫煞亡神"),
        "亡神": ("巳", "卷三·论劫煞亡神"),
        "灾煞": ("子", "卷三·论灾煞"),
        "六厄": ("酉", "卷三·论六厄"),
        "桃花（咸池）": ("卯", "卷二·论咸池"),
        "将星": ("午", "卷二·论将星华盖"),
        "华盖": ("戌", "卷二·论将星华盖"),
    },
    "巳酉丑": {
        "驿马": ("亥", "卷三·论驿马"),
        "劫煞": ("寅", "卷三·论劫煞亡神"),
        "亡神": ("申", "卷三·论劫煞亡神"),
        "灾煞": ("卯", "卷三·论灾煞"),
        "六厄": ("子", "卷三·论六厄"),
        "桃花（咸池）": ("午", "卷二·论咸池"),
        "将星": ("酉", "卷二·论将星华盖"),
        "华盖": ("丑", "卷二·论将星华盖"),
    },
    "亥卯未": {
        "驿马": ("巳", "卷三·论驿马"),
        "劫煞": ("申", "卷三·论劫煞亡神"),
        "亡神": ("寅", "卷三·论劫煞亡神"),
        "灾煞": ("酉", "卷三·论灾煞"),
        "六厄": ("午", "卷三·论六厄"),
        "桃花（咸池）": ("子", "卷二·论咸池"),
        "将星": ("卯", "卷二·论将星华盖"),
        "华盖": ("未", "卷二·论将星华盖"),
    },
}
BRANCH_TO_TRIAD = {
    branch: triad for triad in TRIAD_STARS for branch in triad
}

# 《三命通会》卷三“论孤辰寡宿”开篇所述按年支三方取法。
SOLITARY_LODGING = {
    "亥子丑": {"孤辰": "寅", "寡宿": "戌"},
    "寅卯辰": {"孤辰": "巳", "寡宿": "丑"},
    "巳午未": {"孤辰": "申", "寡宿": "辰"},
    "申酉戌": {"孤辰": "亥", "寡宿": "未"},
}
BRANCH_TO_SEASON_GROUP = {
    branch: group for group in SOLITARY_LODGING for branch in group
}

# Adopt the ten day pillars in the "元白经" list later in this chapter. The
# preceding list in the available transcription contains a conflicting glyph
# for 己丑/乙丑, so this selected table is recorded explicitly.
TEN_EVIL_DAYS = {
    "甲辰", "乙巳", "丙申", "丁亥", "戊戌",
    "己丑", "庚辰", "辛巳", "壬申", "癸亥",
}


def _hits(pillars: dict[str, str], target_branches: set[str]) -> list[str]:
    return [
        name for name, ganzhi in pillars.items()
        if len(ganzhi) >= 2 and ganzhi[1] in target_branches
    ]


def _record(
    name: str,
    pillar_hits: list[str],
    basis: str,
    source: str,
) -> dict[str, str | list[str]]:
    return {
        "名称": name,
        "命中柱位": pillar_hits,
        "起法": basis,
        "出处": f"《三命通会》{source}",
    }


def calculate_sanming_shensha(
    pillars: dict[str, str],
    *,
    day_xunkong: str,
) -> list[dict[str, str | list[str]]]:
    """Find selected explicit rules against four natal pillars; no fortune judgement."""
    if not all(name in pillars for name in ("年柱", "月柱", "日柱", "时柱")):
        return []
    year_pillar = pillars["年柱"]
    day_pillar = pillars["日柱"]
    year_branch = year_pillar[1]
    day_stem = day_pillar[0]
    results: list[dict[str, str | list[str]]] = []

    # Day-stem stars: compare their target branch with each of the four branches.
    lu_branch = LU_BRANCH[day_stem]
    for name, target, source in (
        ("禄神", lu_branch, "卷三·论十干禄"),
        ("金舆", BRANCHES[(BRANCHES.index(lu_branch) + 2) % 12], "卷三·论金舆"),
    ):
        hits = _hits(pillars, {target})
        if hits:
            results.append(_record(name, hits, f"日干{day_stem}，目标地支{target}", source))

    tianyi = set(TIANYI_BRANCHES[day_stem])
    hits = _hits(pillars, tianyi)
    if hits:
        results.append(
            _record("天乙贵人", hits, f"日干{day_stem}，贵人地支{'、'.join(sorted(tianyi, key=BRANCHES.index))}", "卷三·论天乙贵人")
        )

    yangren = YANGREN_BRANCH.get(day_stem)
    if yangren:
        hits = _hits(pillars, {yangren})
        if hits:
            results.append(
                _record("羊刃", hits, f"日干{day_stem}，按书中所述子平取法，羊刃在{yangren}", "卷三·论羊刃")
            )

    # Year-branch triad stars: the book describes these as arising from the birth-year group.
    triad = BRANCH_TO_TRIAD[year_branch]
    for name, (target, source) in TRIAD_STARS[triad].items():
        hits = _hits(pillars, {target})
        if hits:
            results.append(
                _record(name, hits, f"年支{year_branch}属{triad}局，取{target}", source)
            )

    season_group = BRANCH_TO_SEASON_GROUP[year_branch]
    for name, target in SOLITARY_LODGING[season_group].items():
        hits = _hits(pillars, {target})
        if hits:
            results.append(
                _record(name, hits, f"年支{year_branch}属{season_group}，取{target}", "卷三·论孤辰寡宿")
            )

    void_branches = set(day_xunkong)
    hits = _hits(pillars, void_branches)
    if hits:
        results.append(
            _record("旬空（空亡）", hits, f"以日柱{day_pillar}所属旬取{day_xunkong}", "卷三·论空亡")
        )

    if day_pillar in TEN_EVIL_DAYS:
        results.append(
            _record(
                "十恶大败",
                ["日柱"],
                f"日柱{day_pillar}列入本篇元白经所举十日",
                "卷三·论十恶大败（采用元白经列日）",
            )
        )

    return results
