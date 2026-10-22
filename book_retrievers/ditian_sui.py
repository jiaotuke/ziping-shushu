"""《滴天髓》只按日干定位十干专论，保留正文、原注和任氏注的段落。"""

from pathlib import Path
import re

from source_data import make_source_id


SOURCE_FILE = Path(__file__).resolve().parents[1] / "data" / "source" / "滴天髓.txt"
STEM_OPENERS = {
    "甲": "甲木参天", "乙": "乙木虽柔", "丙": "丙火猛烈", "丁": "丁火柔中",
    "戊": "戊土固重", "己": "己土卑湿", "庚": "庚金带煞", "辛": "辛金软弱",
    "壬": "壬水通河", "癸": "癸水至弱",
}


def load_day_stem_records(path: Path = SOURCE_FILE) -> list[dict]:
    """从正文的天干篇中精确分出十干专论；目录、总论和其他篇不入索引。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i, text in enumerate(lines) if re.fullmatch(r"七[、．.]\s*天干", text.strip())]
    if not starts:
        raise ValueError("《滴天髓》正文中未找到‘七、天干’，请核对底本")
    # The last occurrence is the body heading; the first may be in the contents.
    start = starts[-1]
    end = next((i for i in range(start + 1, len(lines)) if re.fullmatch(r"八[、．.]\s*地支", lines[i].strip())), None)
    if end is None:
        raise ValueError("《滴天髓》天干篇结束位置不明，请核对‘八、地支’")
    positions: list[tuple[str, int]] = []
    for stem, opener in STEM_OPENERS.items():
        hits = [i for i in range(start + 1, end) if lines[i].strip().startswith(opener)]
        if len(hits) != 1 or (positions and hits[0] <= positions[-1][1]):
            raise ValueError(f"《滴天髓》{stem}日干专论起句缺失、重复或乱序，请核对底本")
        positions.append((stem, hits[0]))
    citation = "；".join(line[1:].strip() for line in lines if line.startswith("#"))
    records = []
    for index, (stem, begin) in enumerate(positions):
        stop = positions[index + 1][1] if index + 1 < len(positions) else end
        paragraphs = [(i + 1, lines[i].strip()) for i in range(begin, stop) if lines[i].strip()]
        # 己土第二段在当前底本中没有“原注：”标签，保留其原样。
        has_original_note = any(text.startswith("原注：") for _, text in paragraphs)
        has_original_note = has_original_note or (stem == "己" and len(paragraphs) == 3 and paragraphs[1][1].startswith("己土卑薄软湿"))
        if not has_original_note or not any(text.startswith("任氏曰：") for _, text in paragraphs):
            raise ValueError(f"《滴天髓》{stem}日干专论缺少原注或任氏注，请核对底本")
        text = "\n\n".join(paragraph for _, paragraph in paragraphs)
        records.append({
            "source_id": make_source_id(path.name, paragraphs[0][0], text),
            "source_file": path.name,
            "book_name": "滴天髓",
            "citation": citation or "滴天髓阐微电子文本（版本出处未填写）",
            "section": f"论{stem}日干",
            "day_master": stem,
            "line_number": paragraphs[0][0],
            "end_line_number": paragraphs[-1][0],
            "text": text,
        })
    return records


def retrieve(chart: dict, topic: str, count: int, collection) -> dict:
    """日柱天干决定唯一文章，不参与关键词或向量相似度排序。"""
    day_stem = str(chart.get("四柱", {}).get("日柱", ""))[:1]
    day_stem = day_stem or str(chart.get("检索条件", {}).get("day_master", ""))
    if day_stem not in STEM_OPENERS:
        raise ValueError("《滴天髓》需要有效的日干才能定位专论")
    indexed = collection.get(
        where={"$and": [{"book_name": "滴天髓"}, {"day_master": day_stem}]},
        include=["documents", "metadatas"],
    )
    if len(indexed.get("ids", [])) != 1:
        raise ValueError(f"《滴天髓》论{day_stem}日干索引缺失或重复，请重新建立本书索引")
    metadata = dict(indexed["metadatas"][0])
    metadata.update({
        "retrieval_query": f"日干{day_stem} → 论{day_stem}日干",
        "retrieval_method": "按日干精确定位",
        "source_ids": [indexed["ids"][0]],
        "matched_source_id": indexed["ids"][0],
    })
    return {
        "results": [{"document": indexed["documents"][0], "metadata": metadata, "distance": 0.0}],
        "mode": "day_stem_exact", "chapter": f"论{day_stem}日干", "annotation_issues": [],
    }
