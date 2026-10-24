"""Professional chart data using 6tail/lunar-python's existing calendar APIs.

Sources: https://github.com/6tail/lunar-python/blob/master/demo.py
         https://github.com/6tail/lunar-python/tree/master/lunar_python/eightchar
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from functools import lru_cache

from lunar_python import Solar
from lunar_python.util import LunarUtil

from bazi import _self_seat

JIE_KEYS = ("立春", "惊蛰", "清明", "立夏", "芒种", "小暑", "立秋", "白露", "寒露", "立冬", "大雪", "XIAO_HAN", "LI_CHUN")
JIE_LABELS = ("立春", "惊蛰", "清明", "立夏", "芒种", "小暑", "立秋", "白露", "寒露", "立冬", "大雪", "小寒", "立春")
MONTH_BRANCHES = "寅卯辰巳午未申酉戌亥子丑"


def solar_at(value: datetime):
    return Solar.fromYmdHms(value.year, value.month, value.day, value.hour, value.minute, value.second)


def describe_pillar(pillar: str, day_stem: str, *, natal_day: bool = False) -> dict:
    if not pillar:
        return {"pillar": "", "god": "—", "hidden": [], "star": "—", "seat": "—", "void": "—", "nayin": "—"}
    stem, branch = pillar
    return {
        "pillar": pillar, "god": "日主" if natal_day else LunarUtil.SHI_SHEN[day_stem + stem],
        "hidden": [{"stem": h, "god": LunarUtil.SHI_SHEN[day_stem + h]} for h in LunarUtil.ZHI_HIDE_GAN[branch]],
        "star": _self_seat(day_stem, branch), "seat": _self_seat(stem, branch),
        "void": LunarUtil.getXunKong(pillar), "nayin": LunarUtil.NAYIN[pillar],
    }


@lru_cache(maxsize=32)
def luck_cycles(birth_iso: str, gender: str, start_sect: int = 1) -> dict:
    """Use Yun/DaYun/LiuNian directly; age is the library's year-based nominal age."""
    if gender not in ("男", "女") or start_sect not in (1, 2):
        raise ValueError("请选择性别和有效的起运算法。")
    birth = datetime.fromisoformat(birth_iso)
    eight = solar_at(birth).getLunar().getEightChar()
    eight.setSect(2)
    yun = eight.getYun(1 if gender == "男" else 0, start_sect)
    day_stem = eight.getDayGan()
    cycles = []
    for cycle in yun.getDaYun(13):
        if cycle.getEndYear() < cycle.getStartYear():
            continue
        years = []
        for year in cycle.getLiuNian():
            years.append({"id": str(year.getYear()), "label": str(year.getYear()),
                          "note": f"{year.getAge()}虚岁", **describe_pillar(year.getGanZhi(), day_stem)})
        cycles.append({"id": str(cycle.getIndex()),
                       "label": "未起运" if cycle.getIndex() == 0 else f"第{cycle.getIndex()}运",
                       "note": f"{cycle.getStartAge()}—{cycle.getEndAge()}虚岁",
                       "period": f"{cycle.getStartYear()}—{cycle.getEndYear()}",
                       "start_year": cycle.getStartYear(), "end_year": cycle.getEndYear(),
                       "years": years, **describe_pillar(cycle.getGanZhi(), day_stem)})
    return {
        "cycles": cycles,
        "pillars": dict(zip(("年柱", "月柱", "日柱", "时柱"), (eight.getYear(), eight.getMonth(), eight.getDay(), eight.getTime()))),
        "start": yun.getStartSolar().toYmdHms(), "forward": yun.isForward(),
        "start_age": f"{yun.getStartYear()}年{yun.getStartMonth()}个月{yun.getStartDay()}天{yun.getStartHour()}小时",
        "birth": birth_iso, "gender": gender, "start_sect": start_sect,
    }


@lru_cache(maxsize=128)
def flow_months(year: int, day_stem: str) -> list[dict]:
    """Actual solar-term intervals, not calendar months or lunar first days."""
    table = Solar.fromYmdHms(year, 7, 1, 12, 0, 0).getLunar().getJieQiTable()
    bounds = [datetime.fromisoformat(table[key].toYmdHms()) for key in JIE_KEYS]
    months = []
    for index in range(12):
        start, end = bounds[index:index + 2]
        # Asking the library at a point inside the interval avoids duplicating 五虎遁.
        pillar = solar_at(start + (end - start) / 2).getLunar().getMonthInGanZhiExact()
        months.append({"id": str(index), "label": f"{MONTH_BRANCHES[index]}月",
                       "note": f"{JIE_LABELS[index]} → {JIE_LABELS[index + 1]}",
                       "period": f"{start:%m/%d}—{end:%m/%d}",
                       "start": start.isoformat(sep=" "), "end": end.isoformat(sep=" "),
                       **describe_pillar(pillar, day_stem)})
    return months


@lru_cache(maxsize=256)
def flow_days(year: int, month_index: int, day_stem: str) -> list[dict]:
    month = flow_months(year, day_stem)[month_index]
    start, end = datetime.fromisoformat(month["start"]), datetime.fromisoformat(month["end"])
    current = start.date()
    days = []
    while datetime.combine(current, time.min) < end:
        # A transition day may appear in both adjoining month strips; retain its date.
        representative = max(start, datetime.combine(current, time(12)))
        if representative >= end:
            representative = max(start, datetime.combine(current, time.min))
        lunar = solar_at(representative).getLunar()
        days.append({"id": current.isoformat(), "label": f"{current:%m/%d}",
                     "note": f"农历{lunar.getDayInChinese()}", "period": current.isoformat(),
                     **describe_pillar(lunar.getDayInGanZhiExact2(), day_stem)})
        current += timedelta(days=1)
    return days
