"""A small, source-aware retrieval demo for Qiong Tong Bao Jian."""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
from html.parser import HTMLParser

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from source_data import load_source_records
from structured_retrieval import filter_annotations, load_annotations, validate_annotations

ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "data" / "source"
DB_DIR = ROOT / "chroma_db"
COLLECTION_NAME = "bazi_classics_paragraphs"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
SOURCE_URL = (
    "https://raw.githubusercontent.com/garychowcmu/daizhigev20/"
    "master/%E6%98%93%E8%97%8F/%E6%9C%AF%E6%95%B0/%E7%A9%B7%E9%80%9A%E5%AE%9D%E9%89%B4.txt"
)
SOURCE_FILENAME = "穷通宝鉴.txt"
BOOK_SOURCES = [
    {
        "book_name": "穷通宝鉴",
        "filename": SOURCE_FILENAME,
        "url": SOURCE_URL,
        "headers": [
            "# 书名：《穷通宝鉴》",
            "# 电子文本来源：殆知阁古代文献 GitHub，易藏/术数/穷通宝鉴.txt",
            "# 底本版本：该电子文本未注明具体刻本，不能据此认定为某一现代点校版",
        ],
    },
    {
        "book_name": "三命通会",
        "filename": "三命通会.txt",
        "chapter_url": "https://lifeklines.com/library/bazi/san-ming-tong-hui/{page:03d}/",
        "first_chapter_page": 2,
        "last_chapter_page": 381,
        "headers": [
            "# 书名：三命通会",
            "# 电子文本来源：Life K-Lines《三命通会》逐章网页原文",
            "# 整理说明：保留网页原文标点与段落；抓取原文区，不含白话译文；尚未逐页影印校勘",
            "# 章节范围：网页第 2 至 381 页，共 380 个正文篇章",
            "# 来源链接：https://lifeklines.com/library/bazi/san-ming-tong-hui/",
        ],
    },
    {
        "book_name": "子平真诠",
        "filename": "子平真诠.txt",
        "url": "https://raw.githubusercontent.com/Carl-Tsoi/Lucky/main/books/%E5%AD%90%E5%B9%B3%E7%9C%9F%E8%AF%A0.txt",
        "headers": [
            "# 书名：子平真诠",
            "# 电子文本来源：Carl-Tsoi/Lucky GitHub 仓库 books/子平真诠.txt",
            "# 版本内容：子平真诠评注，清沈孝瞻原著；含后人评注，评注者和底本信息需核验",
        ],
    },
    {
        "book_name": "滴天髓",
        "filename": "滴天髓.txt",
        "url": "https://raw.githubusercontent.com/kentang2017/shushubook/main/%E5%91%BD%E7%90%86/%E6%BB%B4%E5%A4%A9%E9%AB%93%E9%98%90%E5%BE%AE-%E6%B8%85-%E4%BB%BB%E9%93%81%E6%A8%B5.txt",
        "headers": [
            "# 书名：滴天髓",
            "# 电子文本来源：kentang2017/shushubook GitHub 仓库 命理/滴天髓阐微-清-任铁樵.txt",
            "# 版本内容：滴天髓阐微，清任铁樵注本；含注释，不是纯滴天髓原文",
        ],
    },
]

STEM_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
MONTH_SEASON = {
    "寅": "三春", "卯": "三春", "辰": "三春",
    "巳": "三夏", "午": "三夏", "未": "三夏",
    "申": "三秋", "酉": "三秋", "戌": "三秋",
    "亥": "三冬", "子": "三冬", "丑": "三冬",
}
MONTH_TITLE = {
    "寅": "正月", "卯": "二月", "辰": "三月", "巳": "四月",
    "午": "五月", "未": "六月", "申": "七月", "酉": "八月",
    "戌": "九月", "亥": "十月", "子": "十一月", "丑": "十二月",
}


def chart_chapter(conditions: dict[str, object], records: list[dict] | None = None) -> str | None:
    """根据日主五行与月令季节，选择《穷通宝鉴》的对应篇章。"""
    day_master = str(conditions.get("day_master", ""))
    month_branch = str(conditions.get("month_branch", ""))
    element = STEM_ELEMENT.get(day_master)
    season = MONTH_SEASON.get(month_branch)
    if not element or not season:
        return None

    if records is None:
        records = load_source_records()
    sections = {str(record["section"]) for record in records}

    # 优先使用书中明确的月份条目，例如“十二月癸水”；没有单月标题时，
    # 再退到季节与日主篇章，例如“正月甲木”归入“三春甲木”。
    month_title = MONTH_TITLE[month_branch]
    month_chapter = f"{month_title}{day_master}{element}"
    if month_chapter in sections:
        return month_chapter
    combined_months = {
        "寅": "正二月", "卯": "正二月", "午": "五六月", "未": "五六月",
        "申": "七八月", "酉": "七八月", "戌": "八九月",
    }
    if month_branch in combined_months:
        combined_chapter = f"{combined_months[month_branch]}{day_master}{element}"
        if combined_chapter in sections:
            return combined_chapter

    chapter = f"{season}{day_master}{element}"
    if chapter in sections:
        return chapter

    # A five-element overview is not a substitute for the requested stem/month.
    return None


def records_in_chapter(
    records: list[dict], chapter: str | None, source_file: str | None = None
) -> list[dict]:
    """只保留当前篇章标题下的原文行。"""
    if not chapter:
        return []
    return [
        record
        for record in records
        if str(record["section"]) == chapter
        and (source_file is None or str(record["source_file"]) == source_file)
    ]


def expand_result_to_chapter(result: dict, source_records: list[dict]) -> dict:
    """把命中的原文行扩展为同一章节全文，并保留组成该章节的出处行 ID。"""
    metadata = dict(result["metadata"])
    chapter_records = records_in_chapter(
        source_records,
        str(metadata.get("chapter", "")),
        str(metadata.get("source_file", "")),
    )
    if not chapter_records:
        return result
    first_line = int(chapter_records[0]["line_number"])
    last_line = int(chapter_records[-1].get("end_line_number", chapter_records[-1]["line_number"]))
    metadata["line_number"] = f"{first_line}-{last_line}"
    metadata["source_ids"] = [str(record["source_id"]) for record in chapter_records]
    metadata["matched_source_id"] = str(result["metadata"].get("source_id", ""))
    return {
        **result,
        "document": "\n".join(str(record["text"]) for record in chapter_records),
        "metadata": metadata,
    }


def ensure_book_texts() -> None:
    """Fetch missing selected book files and normalize them to UTF-8 on the D drive."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for source in BOOK_SOURCES:
        target = SOURCE_DIR / source["filename"]
        if target.exists():
            continue
        print(f"正在下载《{source['book_name']}》文本……")
        if source.get("chapter_url"):
            body = download_chaptered_book(source)
        else:
            with urlopen(source["url"], timeout=60) as response:
                data = response.read()
            if data.startswith((b"\xff\xfe", b"\xfe\xff")):
                body = data.decode("utf-16")
            else:
                try:
                    body = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    body = data.decode("gb18030")
        if len(body.strip()) < 5000:
            raise ValueError(f"《{source['book_name']}》下载内容过短，请检查来源链接。")
        header = "\n".join(source["headers"]) + "\n\n"
        target.write_text(header + body.lstrip("\ufeff\n\r"), encoding="utf-8")
        print(f"全文已保存到 data/source/{source['filename']}。")


class _ChapterArticleParser(HTMLParser):
    """只提取书页标题与原文区的段落，跳过网页导航和白话译文。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.paragraphs: list[str] = []
        self._in_title = False
        self._in_article = False
        self._in_paragraph = False
        self._paragraph_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "h1":
            self._in_title = True
        if tag == "article" and attributes.get("data-testid") == "chapter-original":
            self._in_article = True
        if self._in_article and tag == "p":
            self._in_paragraph = True
            self._paragraph_parts = []
        if self._in_paragraph and tag == "br":
            self._paragraph_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._in_title = False
        if tag == "p" and self._in_paragraph:
            paragraph = "".join(self._paragraph_parts).strip()
            if paragraph:
                self.paragraphs.append(paragraph)
            self._in_paragraph = False
            self._paragraph_parts = []
        if tag == "article":
            self._in_article = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_paragraph:
            self._paragraph_parts.append(data)


def download_chaptered_book(source: dict) -> str:
    """按网页章节下载原文，保留每章标题和网站整理好的段落标点。"""
    pages = range(source["first_chapter_page"], source["last_chapter_page"] + 1)
    cache_dir = ROOT / ".cache" / "sanming_chapter_pages"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_page(page: int) -> tuple[int, str]:
        cache_path = cache_dir / f"{page:03}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            old_title, _, rest = str(cached["chapter"]).partition("\n")
            title = re.sub(r"^第\d+章\s*", "", old_title)
            return page, f"第{page}章 {title}\n{rest}"
        url = source["chapter_url"].format(page=page)
        request = Request(url, headers={"User-Agent": "BaziClassicsStudy/1.0 (local study project)"})
        last_error = None
        for attempt in range(3):
            try:
                with urlopen(request, timeout=45) as response:
                    html = response.read().decode("utf-8")
                parser = _ChapterArticleParser()
                parser.feed(html)
                title = "".join(parser.title_parts).strip()
                if not title or not parser.paragraphs:
                    raise ValueError(f"第 {page} 个网页未能提取章节原文。")
                chapter = f"第{page}章 {title}\n" + "\n".join(parser.paragraphs)
                cache_path.write_text(
                    json.dumps({"chapter": chapter}, ensure_ascii=False), encoding="utf-8"
                )
                return page, chapter
            except Exception as error:
                last_error = error
                if attempt < 2:
                    from time import sleep
                    sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"下载第 {page} 页失败，已重试 3 次：{last_error}")

    chapters_by_page: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch_page, page) for page in pages]
        for completed, future in enumerate(as_completed(futures), start=1):
            page, chapter = future.result()
            chapters_by_page[page] = chapter
            if completed % 50 == 0 or completed == len(futures):
                print(f"已整理 {completed}/{len(futures)} 章……", flush=True)
    if len(chapters_by_page) != len(pages):
        raise ValueError(f"章节数量不完整：预期 {len(pages)}，实际 {len(chapters_by_page)}。")
    return "\n\n".join(chapters_by_page[page] for page in pages)



def get_collection(collection_name: str = COLLECTION_NAME):
    client = chromadb.PersistentClient(path=str(DB_DIR))
    embedding = SentenceTransformerEmbeddingFunction(
        model_name=MODEL_NAME,
        cache_folder=str(ROOT / ".cache" / "huggingface"),
    )
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding,
        metadata={"description": "Source-cited paragraph records from four Chinese classics"},
    )


def ingest(book_name: str | None = None) -> None:
    # Fill any missing book files individually. All files and model caches stay on D:.
    ensure_book_texts()
    all_records = load_source_records()
    records = [record for record in all_records if not book_name or record["book_name"] == book_name]
    if not records:
        print("没有找到正文。请先把有出处的 .txt 文件放入 data/source/，参照 docs/first-rag.md。")
        return

    client = chromadb.PersistentClient(path=str(DB_DIR))
    if book_name is None:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    collection = get_collection()

    if book_name is not None:
        collection.delete(where={"book_name": book_name})

    annotations, annotation_issues = validate_annotations(load_annotations(), all_records)
    annotations_by_source: dict[str, list[dict]] = {}
    for annotation in annotations:
        annotations_by_source.setdefault(annotation["source_id"], []).append(annotation)

    ids, documents, metadatas = [], [], []
    for record in records:
        source_id = str(record["source_id"])
        linked = annotations_by_source.get(source_id, [])
        for alias in record.get("source_aliases", []):
            linked.extend(annotations_by_source.get(str(alias), []))
        linked = list({item["annotation_id"]: item for item in linked}.values())
        ids.append(source_id)
        documents.append(str(record["text"]))
        metadatas.append(
            {
                "source_id": source_id,
                "book_name": record["book_name"],
                "source_file": record["source_file"],
                "citation": record["citation"],
                "chapter": record["section"],
                "line_number": (
                    f"{record['line_number']}-{record['end_line_number']}"
                    if record.get("end_line_number", record["line_number"]) != record["line_number"]
                    else record["line_number"]
                ),
                "end_line_number": record.get("end_line_number", record["line_number"]),
                "annotation_ids": ",".join(a["annotation_id"] for a in linked) or "none",
                "annotation_status": ",".join(a["status"] for a in linked) or "none",
                **({"day_master": record["day_master"]} if record["book_name"] == "滴天髓" else {}),
            }
        )

    # Process small batches: the expanded four-book corpus exceeds Chroma's
    # single-request limit and batching keeps embedding memory predictable.
    batch_size = 256
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
    print(f"已按原文段落索引 {len(documents)} 条。索引保存在 chroma_db/。")
    if annotation_issues:
        print(f"警告：{len(annotation_issues)} 条条件标注未通过出处校验，已排除。")


def search(query: str, count: int) -> None:
    collection = get_collection()
    if collection.count() == 0:
        print("索引为空。请先放入文本并运行：python rag.py ingest")
        return

    # Simple hybrid retrieval: exact phrase matches first, semantic matches after.
    # Remove common question wording so "正月甲木的原文怎么说？" becomes "正月甲木".
    keyword_query = re.sub(
        r"请问|原文|怎么说|是什么|如何|哪些|什么|的|呢|吗|[？?\s]", "", query
    )
    all_items = collection.get(include=["documents", "metadatas"])
    exact_hits = [
        (document, metadata, -1.0)
        for document, metadata in zip(all_items["documents"], all_items["metadatas"])
        if keyword_query and keyword_query in document
    ]

    results = collection.query(
        query_texts=[query],
        n_results=min(max(count * 3, count), collection.count()),
    )
    semantic_hits = list(
        zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    )

    # Keep each paragraph once. Exact matches take priority over vector-only hits.
    seen = {metadata["source_id"] for _, metadata, _ in exact_hits}
    ranked = exact_hits + [
        hit for hit in semantic_hits if hit[1]["source_id"] not in seen
    ]

    for rank, (document, metadata, _distance) in enumerate(ranked[:count], start=1):
        print(
            f"\n[{rank}] {metadata['citation']}｜章节：{metadata['chapter']}｜"
            f"文件：{metadata['source_file']} 第 {metadata['line_number']} 行（段落）｜"
            f"引用ID：{metadata['source_id']}"
        )
        print(document)


def search_chart(topic: str, count: int, conditions: dict[str, object]) -> None:
    """先按人工标注的命盘条件过滤，再对候选原文做语义排序。"""
    ranked, annotation_issues = retrieve_chart_records(topic, count, conditions)
    if annotation_issues:
        print(f"提示：{len(annotation_issues)} 条条件标注未通过出处校验，已排除。")
    if not ranked:
        print("没有匹配的结构化条件标注或索引记录。")
        return
    for rank, result in enumerate(ranked, start=1):
        metadata = result["metadata"]
        annotation = result["annotation"]
        print(
            f"\n[{rank}] 原文出处：{metadata['citation']}｜章节：{metadata['chapter']}｜"
            f"{metadata['source_file']} 第 {metadata['line_number']} 行（段落）｜"
            f"引用ID：{metadata['source_id']}｜条件标注：{annotation['status']}"
        )
        print(result["document"])


def retrieve_chart_records(
    topic: str, count: int, conditions: dict[str, object], collection=None
) -> tuple[list[dict], list[str]]:
    """先定位日主季节篇章，再筛选条件标注，并只在篇章候选内做向量排序。"""
    source_records = load_source_records("穷通宝鉴")
    chapter = chart_chapter(conditions, source_records)
    chapter_records = records_in_chapter(source_records, chapter)
    chapter_aliases = {
        source_id
        for record in chapter_records
        for source_id in [str(record["source_id"]), *(str(x) for x in record.get("source_aliases", []))]
    }
    record_by_alias = {
        source_id: record
        for record in chapter_records
        for source_id in [str(record["source_id"]), *(str(x) for x in record.get("source_aliases", []))]
    }
    annotations, annotation_issues = validate_annotations(
        load_annotations(), source_records
    )
    matched = [
        annotation
        for annotation in filter_annotations(annotations, conditions)
        if str(annotation["source_id"]) in chapter_aliases
    ]
    source_ids = sorted({str(record_by_alias[item["source_id"]]["source_id"]) for item in matched})
    if not source_ids:
        return [], annotation_issues
    collection = collection or get_collection()
    if collection.count() == 0:
        return [], annotation_issues
    indexed_ids = set(collection.get(include=[])["ids"])
    source_ids = [source_id for source_id in source_ids if source_id in indexed_ids]
    if not source_ids:
        return [], annotation_issues

    results = collection.query(
        query_texts=[topic],
        n_results=min(max(count, 1), len(source_ids)),
        where={"source_id": {"$in": source_ids}},
    )
    annotation_by_source: dict[str, list[dict]] = {}
    for annotation in matched:
        paragraph_id = str(record_by_alias[annotation["source_id"]]["source_id"])
        annotation_by_source.setdefault(paragraph_id, []).append(annotation)
    ranked = []
    for document, metadata, distance in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        ranked.append(
            {
                "document": document,
                "metadata": metadata,
                "annotation": annotation_by_source[metadata["source_id"]][0],
                "distance": distance,
            }
        )
    return [expand_result_to_chapter(item, source_records) for item in ranked], annotation_issues


def retrieve_chapter_references(
    topic: str,
    conditions: dict[str, object],
    count: int = 3,
    collection=None,
) -> tuple[list[dict], str | None]:
    """在命盘对应的日主季节篇章内做语义参考检索，不代表条件适用。"""
    records = load_source_records("穷通宝鉴")
    chapter = chart_chapter(conditions, records)
    chapter_records = records_in_chapter(records, chapter)
    source_ids = [str(record["source_id"]) for record in chapter_records]
    if not source_ids:
        return [], chapter

    collection = collection or get_collection()
    indexed_ids = set(collection.get(include=[])["ids"])
    source_ids = [source_id for source_id in source_ids if source_id in indexed_ids]
    if not source_ids:
        return [], chapter

    results = collection.query(
        query_texts=[topic],
        n_results=min(max(count, 1), len(source_ids)),
        where={"source_id": {"$in": source_ids}},
    )
    ranked = [
        {"document": document, "metadata": metadata, "distance": distance}
        for document, metadata, distance in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        )
    ]
    return [expand_result_to_chapter(item, records) for item in ranked], chapter


def retrieve_book_references(
    book_name: str, topic: str, count: int = 1, collection=None
) -> list[dict]:
    """在指定古籍内做语义参考检索，返回原文记录及其出处。"""
    records = load_source_records(book_name)
    if not records:
        return []
    collection = collection or get_collection()
    results = collection.query(
        query_texts=[topic],
        n_results=min(max(count, 1), len(records)),
        where={"book_name": book_name},
    )
    ranked = [
        {"document": document, "metadata": metadata, "distance": distance}
        for document, metadata, distance in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        )
    ]
    return ranked


def retrieve_semantic_references(topic: str, count: int = 3, collection=None) -> list[dict]:
    """Return source-cited whole-book matches without claiming condition applicability."""
    collection = collection or get_collection()
    total = collection.count()
    if total == 0:
        return []

    results = collection.query(
        query_texts=[topic],
        n_results=min(max(count, 1), total),
    )
    return [
        {"document": document, "metadata": metadata, "distance": distance}
        for document, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="《穷通宝鉴》原文语义检索练习")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest_parser = commands.add_parser("ingest", help="按完整原文段落建立本地向量索引")
    ingest_parser.add_argument("--book", help="只更新指定书籍的索引，保留其他书籍")
    search_parser = commands.add_parser("search", help="检索相关原文")
    search_parser.add_argument("query", help="自然语言问题或关键词")
    search_parser.add_argument("-k", type=int, default=3, help="返回结果数（默认 3）")
    chart_parser = commands.add_parser(
        "search-chart", help="先按结构化命盘条件筛选，再按报告主题排序"
    )
    chart_parser.add_argument("--topic", required=True, help="报告主题，例如：春木调候")
    chart_parser.add_argument("--day-master", required=True, help="日主天干，例如：甲")
    chart_parser.add_argument("--month-branch", required=True, help="月令地支，例如：寅")
    chart_parser.add_argument("--exposed-stems", default="", help="透干列表，逗号分隔")
    chart_parser.add_argument("--hidden-stems", default="", help="藏干列表，逗号分隔")
    chart_parser.add_argument("-k", type=int, default=3, help="返回结果数（默认 3）")
    args = parser.parse_args()

    if args.command == "ingest":
        ingest(args.book)
    elif args.command == "search-chart":
        search_chart(
            args.topic,
            args.k,
            {
                "day_master": args.day_master,
                "month_branch": args.month_branch,
                "exposed_stems": [s for s in args.exposed_stems.split(",") if s],
                "hidden_stems": [s for s in args.hidden_stems.split(",") if s],
            },
        )
    else:
        search(args.query, args.k)


if __name__ == "__main__":
    main()
