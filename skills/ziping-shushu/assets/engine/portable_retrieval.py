"""Device-local paragraph ranking behind the existing per-book retrieval rules.

Exact day-stem/month/chapter selection is unchanged. Only vector fallback is
replaced with transparent character-bigram BM25 ranking in portable builds.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from threading import RLock

from source_data import load_source_records, source_version


def tokens(text: str) -> list[str]:
    words = re.findall(r"[\u3400-\u9fff]+|[A-Za-z0-9]+", text)
    return [token for word in words for token in
            ([word.lower()] if word.isascii() or len(word) == 1 else [word[i:i+2] for i in range(len(word)-1)])]


def _matches(meta: dict, where: dict | None) -> bool:
    if not where:
        return True
    for key, expected in where.items():
        if key == "$and":
            if not all(_matches(meta, item) for item in expected):
                return False
        elif key == "$or":
            if not any(_matches(meta, item) for item in expected):
                return False
        elif isinstance(expected, dict):
            if "$in" in expected and meta.get(key) not in expected["$in"]:
                return False
            if "$eq" in expected and meta.get(key) != expected["$eq"]:
                return False
        elif meta.get(key) != expected:
            return False
    return True


class PortableCollection:
    reference_mode = "local_text_reference"

    def __init__(self):
        self.records = load_source_records()
        self.entries = []
        self._ranking = None
        self._ranking_lock = RLock()
        for record in self.records:
            meta = {"source_id": str(record["source_id"]), "book_name": record["book_name"],
                    "source_file": record["source_file"], "chapter": record["section"],
                    "line_number": f"{record['line_number']}-{record.get('end_line_number',record['line_number'])}",
                    "citation": record["citation"], "retrieval_method": "本地段落关键词排序（非向量检索）"}
            if record.get("day_master"):
                meta["day_master"] = record["day_master"]
            self.entries.append((record, meta))

    def _ranking_data(self):
        """Defer corpus tokenization until a book needs BM25 fallback ranking."""
        with self._ranking_lock:
            if self._ranking is None:
                entries = []
                df = Counter()
                for record, meta in self.entries:
                    counts = Counter(tokens(str(record["section"]) + " " + str(record["text"])))
                    df.update(counts.keys())
                    entries.append((record, meta, counts, sum(counts.values())))
                average = sum(e[3] for e in entries) / max(len(entries), 1)
                # Publish only the completed index so concurrent queries never
                # observe partial document frequencies or incomplete entries.
                self._ranking = (entries, df, average)
            return self._ranking

    def count(self):
        return len(self.entries)

    def get(self, *, where=None, include=None, ids=None):
        entries = [e for e in self.entries if _matches(e[1], where) and (ids is None or e[1]["source_id"] in ids)]
        return {"ids": [e[1]["source_id"] for e in entries],
                "documents": [e[0]["text"] for e in entries], "metadatas": [dict(e[1]) for e in entries]}

    def query(self, *, query_texts, n_results=1, where=None, **_):
        entries, df, average = self._ranking_data()
        output = {"ids": [], "documents": [], "metadatas": [], "distances": []}
        for query in query_texts:
            terms = set(tokens(query))
            ranked = []
            for record, meta, counts, length in entries:
                if not _matches(meta, where):
                    continue
                score = sum(math.log(1 + (len(entries) - df[t] + .5) / (df[t] + .5))
                            * counts[t] * 2.2 / (counts[t] + 1.2 * (.25 + .75 * length / max(average, 1)))
                            for t in terms if counts[t])
                ranked.append((score, int(record["line_number"]), record, meta))
            ranked.sort(key=lambda row: (-row[0], row[1], row[3]["source_id"]))
            hits = ranked[:max(1, int(n_results))]
            for key, value in (("ids", [r[3]["source_id"] for r in hits]),
                               ("documents", [r[2]["text"] for r in hits]),
                               ("metadatas", [dict(r[3]) for r in hits]),
                               ("distances", [1 / (1 + r[0]) for r in hits])):
                output[key].append(value)
        return output


@lru_cache(maxsize=1)
def _collection_for_version(_source_version: tuple):
    return PortableCollection()


_COLLECTION_LOCK = RLock()


def get_collection():
    with _COLLECTION_LOCK:
        return _collection_for_version(source_version())


def retrieve_chart(chart: dict) -> dict:
    from book_retrievers.registry import retrieve

    conditions = chart["检索条件"]
    topic = "；".join([*(f"{key}{value}" for key, value in chart["四柱"].items()),
                      "日主" + conditions["day_master"], "月令" + conditions["month_branch"],
                      "透干" + "、".join(conditions.get("exposed_stems", []))])
    results, modes, errors = {}, {}, {}
    import sys
    for book in ("穷通宝鉴", "三命通会", "子平真诠", "滴天髓"):
        try:
            found = retrieve(book, chart, topic, 1, get_collection(), sys.modules[__name__])
            results[book], modes[book] = found["results"], found["mode"]
        except (ValueError, OSError, KeyError) as error:
            results[book], errors[book] = [], str(error)
    return {"success": any(results.values()), "results_by_book": results, "book_modes": modes,
            "book_errors": errors, "ranking": "本地段落关键词排序；日干、月令及指定篇章仍按原规则定位"}
