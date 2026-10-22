"""《子平真诠》检索：按用神、月令及十神专论的篇章体系选篇。"""

from .common import retrieve_sections


def retrieve(chart: dict, topic: str, count: int, collection) -> dict:
    gods = {
        str(item.get("天干十神", ""))
        for item in chart.get("四柱详情", {}).values()
    }
    for details in chart.get("四柱详情", {}).values():
        gods.update(str(item.get("十神", "")) for item in details.get("地支藏干", []))

    chapters = ["论用神", "论月令", "论用神配气候"]
    god_chapters = {
        "正官": ["论正官"], "七杀": ["论偏官"], "偏官": ["论偏官"],
        "正财": ["论财", "论财取运"], "偏财": ["论财", "论财取运"],
        "正印": ["论印绶"], "偏印": ["论印绶"], "食神": ["论食神"],
        "伤官": ["论伤官"], "比肩": ["论建禄月劫", "论阳刃"],
        "劫财": ["论建禄月劫", "论阳刃"],
    }
    for god in gods:
        chapters.extend(god_chapters.get(god, []))
    focused_topic = topic + "；《子平真诠》篇章线索：" + "、".join(sorted(gods))
    results, mode, chapter = retrieve_sections(
        "子平真诠", focused_topic, chapters, collection, count
    )
    return {"results": results, "mode": mode, "chapter": chapter, "annotation_issues": []}
