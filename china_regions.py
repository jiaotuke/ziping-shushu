"""Offline administrative-region choices with approximate administrative centers.

The browser path never fetches a remote URL. A bundled snapshot is preferred;
old, already-downloaded DataV files are a migration fallback only when the
snapshot is absent. Missing data is reported rather than replaced by a guessed
location. See data/regions/SOURCE.md for coverage and coordinate provenance.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from runtime_paths import CACHE_ROOT, RESOURCE_ROOT

REGION_SNAPSHOT = RESOURCE_ROOT / "data" / "regions" / "china_regions.json"
REGION_DATA_DIR = CACHE_ROOT / "china_admin"
REGION_SOURCE_LABEL = "AreaCity 离线行政区划快照（2026-04-03）"


class RegionDataUnavailable(OSError):
    """The requested local administrative data cannot be used safely."""


def _stamp(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=4)
def _snapshot(path: str, _mtime_ns: int, _size: int) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not isinstance(data.get("children"), dict):
            raise ValueError("快照格式不正确")
        return data
    except (OSError, ValueError, TypeError) as error:
        raise RegionDataUnavailable(f"本地地区快照无法读取：{error}") from error


@lru_cache(maxsize=512)
def _legacy(path: str, _mtime_ns: int, _size: int) -> tuple[tuple, ...]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        regions = []
        for feature in data.get("features", []):
            props = feature.get("properties") or {}
            center = props.get("center")
            if props.get("name") and props.get("adcode") and center and len(center) >= 2:
                regions.append((props["name"], str(props["adcode"]), center[0], center[1],
                                int(props.get("childrenNum") or 0)))
        return tuple(regions)
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise RegionDataUnavailable(f"本地地区缓存无法读取：{error}") from error


def load_regions(adcode: str) -> list[dict]:
    """Return one hierarchy level using the existing five-field UI contract.

    Each call returns fresh dictionaries so callers cannot mutate shared cached
    records. Null coordinates represent an explicitly unavailable center; the
    UI must not use such a record for true-solar-time correction.
    """
    code = str(adcode).strip()
    if not code.isascii() or not code.isdecimal() or len(code) != 6:
        raise RegionDataUnavailable("地区编码不正确，请重新选择出生地点。")
    if REGION_SNAPSHOT.exists():
        data = _snapshot(*_stamp(REGION_SNAPSHOT))
        rows = data["children"].get(code)
        if rows is None:
            raise RegionDataUnavailable(f"离线快照中没有地区 {code}，请更新地区资料或明确选择其他地点。")
    else:
        cached_file = REGION_DATA_DIR / f"{code}_full.json"
        if not cached_file.is_file():
            raise RegionDataUnavailable(
                f"本地缺少地区 {code} 的资料；请补齐 data/regions 地区快照。程序没有联网或替换坐标。")
        rows = _legacy(*_stamp(cached_file))
    return [{"name": row[0], "adcode": str(row[1]), "longitude": row[2],
             "latitude": row[3], "children_num": int(row[4])} for row in rows]
