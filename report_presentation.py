"""Plain-language report summaries; never derive domain conclusions from an overall score."""

from __future__ import annotations

import re

PRESENTATION_VERSION = "results-first-v5"
LIFE_DOMAINS = (("career", "事业与学业"), ("wealth", "财务与资源"), ("relationship", "感情与合作"))

PRESENTATION_INSTRUCTIONS = """
这是面向普通用户的第五版报告。先完成命盘、作用及条件判断，再独立提炼overview和life_domains；不要根据一个综合分倒推三个方面的结论。
overview.headline用一句白话说明总体倾向，opportunity说明一个可把握的方向，caution说明一个值得留意的地方。
life_domains必须按所给三个key各返回一项：事业与学业、财务与资源、感情与合作，每项summary是一句有条件的白话结论，advice是一条可执行的日常建议。三方面分别分析，不复制同一句套话，不把综合分当作三方面评分，不编造分数。
摘要和三张卡片避免身强、用神、七杀、刑冲等未解释术语；如确有必要，用普通人能理解的意思表达。保留不确定性和成立条件，不作绝对承诺；详细推导保留在原有字段，摘要不能替代依据。
沿用旧报告三个领域：事业与学业、财务与资源、感情与合作。结合已提供年龄给适宜场景；缺少现实信息时明确适用条件，不假定在职、在校、已婚或特定经历。情感可涵盖亲密关系与重要的人际沟通。
有适用原文再附citations；没有则为空，不强凑。白话摘要须忠于本段详细判断，不能引入推导中没有的新事件或承诺。
""".strip()


def presentation_schema():
    return {
        "overview": {"headline": "一句白话总评", "opportunity": "一个可把握的方向", "caution": "一个留意事项"},
        "life_domains": [{"key": key, "summary": "一句有条件的白话结论", "advice": "一条日常建议", "citations": []}
                         for key, _ in LIFE_DOMAINS],
    }


def validate_presentation(document):
    from ai_analysis import AIError

    overview = document.get("overview")
    if not isinstance(overview, dict) or not all(isinstance(overview.get(k), str) and overview[k].strip()
                                                for k in ("headline", "opportunity", "caution")):
        raise AIError("第五版报告缺少白话总评、机会或留意事项。")
    cards = document.get("life_domains")
    expected = [key for key, _ in LIFE_DOMAINS]
    if (not isinstance(cards, list) or len(cards) != len(expected)
            or not all(isinstance(c, dict) and isinstance(c.get("key"), str) for c in cards)
            or {c["key"] for c in cards} != set(expected)):
        raise AIError("第五版报告须分别提供事业与学业、财务与资源、感情与合作三项，不得遗漏或重复。")
    by_key = {c["key"]: c for c in cards}
    document["life_domains"] = [by_key[key] for key in expected]
    for card in document["life_domains"]:
        if not all(isinstance(card.get(k), str) and card[k].strip() for k in ("summary", "advice")):
            raise AIError(f"第五版报告的 {card['key']} 卡片缺少白话结论或建议。")
        card.setdefault("citations", [])
    document["presentation_version"] = PRESENTATION_VERSION


def _excerpt(value):
    """Labelled legacy excerpt only; do not invent a new model interpretation."""
    text = str(value or "").strip()
    sentence = re.split(r"(?<=[。！？])", text, maxsplit=1)[0]
    return sentence[:100] + ("…" if len(sentence) > 100 else "")


def presentation_view(document):
    """Keep old paid reports readable, explicitly leaving missing domains unfilled."""
    overview = document.get("overview")
    modern = (isinstance(overview, dict) and all(isinstance(overview.get(k), str) and overview[k].strip()
                                              for k in ("headline", "opportunity", "caution")))
    if not modern:
        overview = {"headline": _excerpt(document.get("assessment") or document.get("summary")) or "查看本次报告",
                    "opportunity": "", "caution": ""}
    supplied = {c.get("key"): c for c in document.get("life_domains", []) if isinstance(c, dict)}
    legacy = {d.get("name"): d for d in document.get("domains", []) if isinstance(d, dict)}
    mapping = {"wealth": "财务与资源", "career": "事业与学业", "relationship": "感情与合作"}
    cards = []
    for key, label in LIFE_DOMAINS:
        card = supplied.get(key)
        if card and all(isinstance(card.get(k), str) and card[k].strip() for k in ("summary", "advice")):
            cards.append({"key": key, "label": label, "summary": card["summary"], "advice": card["advice"], "legacy": False})
        else:
            old = legacy.get(mapping.get(key), {})
            cards.append({"key": key, "label": label, "summary": _excerpt(old.get("assessment")) or "旧报告未单独提供这一项。",
                          "advice": "", "legacy": True,
                          "note": "旧报告说明摘录，完整内容见后文。" if old else "重新生成第五版报告后可补充；不会自动调用模型。"})
    return {"overview": overview, "cards": cards, "legacy": not modern or any(c["legacy"] for c in cards)}
