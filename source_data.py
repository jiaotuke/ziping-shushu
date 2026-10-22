"""Load source paragraphs and stable identifiers anchored to original lines."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "data" / "source"
ZIPING_CHAPTERS_FILE = ROOT / "data" / "annotations" / "ziping_chapters.json"


def ziping_chapter_boundaries(lines: list[str]) -> dict[int, str]:
    """Resolve edition-specific chapter anchors, rejecting missing or stale anchors."""
    data = json.loads(ZIPING_CHAPTERS_FILE.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("source_file") != "子平真诠.txt":
        raise ValueError("《子平真诠》篇章位置记录的格式不正确")
    boundaries: dict[int, str] = {}
    previous = 0
    for chapter in data["chapters"]:
        quote = chapter.get("start_quote", "")
        hits = [number for number, line in enumerate(lines, start=1) if quote and line.strip().startswith(quote)]
        if len(hits) != 1 or hits[0] <= previous:
            raise ValueError(f"《子平真诠》篇章起句失效或顺序错误：{chapter['title']}，请核对底本")
        previous = hits[0]
        boundaries[previous] = f"第{chapter['number']}篇 {chapter['title']}"
    return boundaries

HEADING_PATTERN = re.compile(
    r"^(第[一二三四五六七八九十百零〇\d]+[章节卷篇部].*|卷[上中下].*|"
    r".*卷[一二三四五六七八九十百零〇\d]+|卷[上中下].*|"
    r"六[甲乙丙丁戊己庚辛壬癸]日[子丑寅卯辰巳午未申酉戌亥]时断|"
    r"五行总论|论[^，。！？；、,.!?;]{1,30}|三[春夏秋冬].+|"
    r"[正二三四五六七八九十冬孟仲季]+月[^，。！？；、,.!?;]{1,30}|"
    r"[一二三四五六七八九十百]+[、.．][^，。！？；、,.!?;]{1,35}|"
    r"[上下]篇[^，。！？；、,.!?;]{1,30}|目录|序|凡例)$"
)


def make_source_id(filename: str, line_number: int, text: str) -> str:
    """Stable for unchanged source line; detects stale annotations after edits."""
    raw = f"{filename}:{line_number}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_source_records(book_name: str | None = None) -> list[dict[str, object]]:
    """Return paragraph-sized source records with their original line ranges."""
    records: list[dict[str, object]] = []
    for path in sorted(SOURCE_DIR.glob("*.txt")):
        lines = path.read_text(encoding="utf-8").splitlines()
        citation = "；".join(line[1:].strip() for line in lines if line.startswith("#"))
        title_line = next((line for line in lines if line.startswith("# 书名：")), "")
        title = title_line.removeprefix("# 书名：").strip().strip("《》") or path.stem
        if book_name and title != book_name:
            continue
        if title == "滴天髓":
            from book_retrievers.ditian_sui import load_day_stem_records

            records.extend(load_day_stem_records(path))
            continue
        first_body_line = 1
        chapter_boundaries: dict[int, str] = {}
        if title == "子平真诠":
            chapter_boundaries = ziping_chapter_boundaries(lines)
            # This transcription has a table of contents followed by a second
            # "序" heading that starts the actual text. Do not index TOC entries
            # as empty chapters that can outrank their full body chapters.
            preface_lines = [
                number
                for number, line in enumerate(lines, start=1)
                if line.strip() == "序"
            ]
            if len(preface_lines) >= 2:
                first_body_line = preface_lines[1]
        section = "未识别章节"
        paragraph_lines: list[tuple[int, str]] = []

        def flush_paragraph() -> None:
            if not paragraph_lines:
                return
            start_line = paragraph_lines[0][0]
            end_line = paragraph_lines[-1][0]
            paragraph_text = "".join(item for _, item in paragraph_lines).strip()
            aliases = [
                make_source_id(path.name, number, item.strip())
                for number, item in paragraph_lines
            ]
            records.append(
                {
                    # Keep a stable anchor ID so existing one-line citations remain valid.
                    "source_id": aliases[0],
                    "source_aliases": aliases,
                    "source_file": path.name,
                    "book_name": title,
                    "citation": citation
                    or (
                        "殆知阁古代文献 GitHub 电子转录；具体底本和页码未注明"
                        if path.name == "穷通宝鉴.txt"
                        else f"文件：{path.name}（版本出处未填写）"
                    ),
                    "section": section,
                    "line_number": start_line,
                    "end_line_number": end_line,
                    "text": paragraph_text,
                }
            )
            paragraph_lines.clear()

        for line_number, raw in enumerate(lines, start=1):
            if line_number < first_body_line:
                continue
            if line_number in chapter_boundaries:
                flush_paragraph()
                section = chapter_boundaries[line_number]
            text = raw.strip()
            if not text or raw.startswith("#"):
                flush_paragraph()
                continue
            heading_text = text.rstrip("：:")
            is_heading = (
                len(heading_text) <= 40
                and not re.search(r"[，。！？；,.!?;]", heading_text)
                and bool(HEADING_PATTERN.fullmatch(heading_text))
            )
            # Correct 十一月 headings only for this book; preserve other segmentation.
            if title == "穷通宝鉴" and re.fullmatch(
                r"[正一二三四五六七八九十冬腊]+月[甲乙丙丁戊己庚辛壬癸][木火土金水]", heading_text
            ):
                is_heading = True
            if is_heading:
                flush_paragraph()
                if not chapter_boundaries:
                    section = heading_text
                elif heading_text == "序":
                    section = "序"
                paragraph_lines.append((line_number, text))
                flush_paragraph()
                continue

            # A missing terminal mark usually means a source line continues the
            # same paragraph. Keep sentence-ended lines as separate chunks.
            if paragraph_lines and re.search(r"[。！？!?；]$", paragraph_lines[-1][1].rstrip()):
                flush_paragraph()
            paragraph_lines.append((line_number, text))
        flush_paragraph()
    return records
