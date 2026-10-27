"""用 lunar-python 把公历出生时间换算成四柱。"""

from __future__ import annotations

import argparse
import math
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lunar_python import Lunar, LunarYear, Solar
from lunar_python.util import LunarUtil
from sanming_shensha import calculate_sanming_shensha


_EARTHLY_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
_CHANG_SHENG = ("长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养")
# lunar-python 的十二长生起点；阳干顺行，阴干逆行。
_CHANG_SHENG_START = {"甲": 1, "丙": 10, "戊": 10, "庚": 7, "壬": 4,
                      "乙": 6, "丁": 9, "己": 9, "辛": 0, "癸": 3}


def _self_seat(stem: str, branch: str) -> str:
    """计算该柱天干在本柱地支上的十二长生位置（自坐）。"""
    start = _CHANG_SHENG_START[stem]
    branch_index = _EARTHLY_BRANCHES.index(branch)
    direction = 1 if stem in "甲丙戊庚壬" else -1
    return _CHANG_SHENG[(start + direction * branch_index) % 12]


def calculate_chart(
    birth_time: datetime,
    sect: int = 2,
    *,
    time_basis: str = "按输入的当地民用钟表时间，未校正真太阳时",
) -> dict[str, object]:
    """计算四柱；sect 1/2 是 lunar-python 对日柱换日的两种规则。"""
    if sect not in (1, 2):
        raise ValueError("sect 只能是 1 或 2")

    # lunar-python 接收公历年月日时分秒；时间修正由调用方明确完成。
    solar = Solar.fromYmdHms(
        birth_time.year,
        birth_time.month,
        birth_time.day,
        birth_time.hour,
        birth_time.minute,
        birth_time.second,
    )
    lunar = solar.getLunar()
    eight_char = lunar.getEightChar()
    eight_char.setSect(sect)

    pillars = {
        "年柱": eight_char.getYear(),
        "月柱": eight_char.getMonth(),
        "日柱": eight_char.getDay(),
        "时柱": eight_char.getTime(),
    }
    pillar_methods = {
        "年柱": "Year",
        "月柱": "Month",
        "日柱": "Day",
        "时柱": "Time",
    }
    pillar_details: dict[str, dict[str, object]] = {}
    for pillar_name, method_suffix in pillar_methods.items():
        pillar = pillars[pillar_name]
        hidden_stems = getattr(eight_char, f"get{method_suffix}HideGan")()
        hidden_gods = getattr(eight_char, f"get{method_suffix}ShiShenZhi")()
        pillar_details[pillar_name] = {
            "天干十神": getattr(eight_char, f"get{method_suffix}ShiShenGan")(),
            "地支藏干": [
                {"天干": stem, "十神": god}
                for stem, god in zip(hidden_stems, hidden_gods)
            ],
            "纳音": getattr(eight_char, f"get{method_suffix}NaYin")(),
            "旬空": getattr(eight_char, f"get{method_suffix}XunKong")(),
            "五行": getattr(eight_char, f"get{method_suffix}WuXing")(),
            "星运": getattr(eight_char, f"get{method_suffix}DiShi")(),
            "自坐": _self_seat(pillar[0], pillar[1]),
        }
    stems = [pillar[0] for pillar in pillars.values()]
    hidden_stems = (
        eight_char.getYearHideGan()
        + eight_char.getMonthHideGan()
        + eight_char.getDayHideGan()
        + eight_char.getTimeHideGan()
    )
    natal_shensha = calculate_sanming_shensha(
        pillars,
        day_xunkong=eight_char.getDayXunKong(),
    )
    return {
        "公历": birth_time.strftime("%Y-%m-%d %H:%M:%S"),
        "农历": lunar.toString(),
        "四柱": pillars,
        "四柱详情": pillar_details,
        "命局神煞": natal_shensha,
        "检索条件": {
            "day_master": eight_char.getDayGan(),
            "month_branch": eight_char.getMonthZhi(),
            "exposed_stems": sorted(set(stems)),
            "hidden_stems": sorted(set(hidden_stems)),
        },
        "日柱换日规则": f"lunar-python sect={sect}",
        "时间说明": time_basis,
    }


def calculate_pillars_chart(pillars: dict[str, str]) -> dict[str, object]:
    """Build the same chart data directly from supplied pillars, without inventing a date."""
    names = ("年柱", "月柱", "日柱", "时柱")
    stems = "甲乙丙丁戊己庚辛壬癸"
    if not isinstance(pillars, dict) or set(pillars) != set(names):
        raise ValueError("请完整填写年柱、月柱、日柱、时柱。")
    normalized = {}
    for name in names:
        value = pillars[name]
        value = "".join(value.split()) if isinstance(value, str) else ""
        if not value:
            raise ValueError(f"请填写{name}，例如甲子。")
        if value not in LunarUtil.JIA_ZI:
            raise ValueError(f"{name}“{value}”不是有效的六十甲子，请填写一个天干和一个地支，例如甲子、乙丑。")
        normalized[name] = value
    year, month, day, hour = (normalized[name] for name in names)
    # Five-tiger month rule, beginning at 寅; five-rat hour rule, beginning at 子.
    month_index = (_EARTHLY_BRANCHES.index(month[1]) - 2) % 12
    expected_month = stems[(stems.index(year[0]) % 5 * 2 + 2 + month_index) % 10] + month[1]
    if month != expected_month:
        raise ValueError(f"年柱与月柱不一致：按{year[0]}年五虎遁，{month[1]}月应为{expected_month}，请核对输入。")
    expected_hour = stems[(stems.index(day[0]) % 5 * 2 + _EARTHLY_BRANCHES.index(hour[1])) % 10] + hour[1]
    # sect=2 can keep the prior day at 23:00 while the hour follows the next day.
    late_zi = hour[1] == "子" and hour[0] == stems[((stems.index(day[0]) + 1) % 5 * 2) % 10]
    if hour != expected_hour and not late_zi:
        raise ValueError(f"日柱与时柱不一致：按{day[0]}日五鼠遁，{hour[1]}时应为{expected_hour}，请核对输入。")
    day_stem = day[0]
    details = {}
    hidden_all = []
    for name, pillar in normalized.items():
        stem, branch = pillar
        hidden = LunarUtil.ZHI_HIDE_GAN[branch]
        hidden_all.extend(hidden)
        details[name] = {
            "天干十神": "日主" if name == "日柱" else LunarUtil.SHI_SHEN[day_stem + stem],
            "地支藏干": [{"天干": h, "十神": LunarUtil.SHI_SHEN[day_stem + h]} for h in hidden],
            "纳音": LunarUtil.NAYIN[pillar],
            "旬空": LunarUtil.getXunKong(pillar),
            "五行": LunarUtil.WU_XING_GAN[stem] + LunarUtil.WU_XING_ZHI[branch],
            "星运": _self_seat(day_stem, branch),
            "自坐": _self_seat(stem, branch),
        }
    return {
        "输入历法": "四柱八字", "四柱": normalized, "四柱详情": details,
        "命局神煞": calculate_sanming_shensha(normalized, day_xunkong=LunarUtil.getXunKong(day)),
        "检索条件": {"day_master": day_stem, "month_branch": month[1],
                     "exposed_stems": sorted({p[0] for p in normalized.values()}),
                     "hidden_stems": sorted(set(hidden_all))},
        "日柱换日规则": "直接使用输入日柱，不进行日期换算或换日处理",
        "时间说明": "按用户填写的四柱直接排盘，未提供公历出生日期，不进行真太阳时修正"
                    + ("；子时日时搭配可对应晚子时次日时干取法，保留输入，不反推日期" if late_zi else ""),
    }


@lru_cache(maxsize=128)
def find_pillar_birth_times(
    year_pillar: str, month_pillar: str, day_pillar: str, hour_pillar: str,
    latest_date: date,
) -> tuple[str, ...]:
    """Return matching dates with a library-selected hour, without choosing a birth year."""
    names = ("年柱", "月柱", "日柱", "时柱")
    pillars = calculate_pillars_chart(dict(zip(names, (year_pillar, month_pillar, day_pillar, hour_pillar))))["四柱"]
    matches = set()
    for solar in Solar.fromBaZi(*(pillars[name] for name in names), sect=2, base_year=1800):
        birth = datetime.fromisoformat(solar.toYmdHms())
        if date(1800, 1, 1) <= birth.date() <= latest_date:
            # Keep the library's valid time at solar-term boundaries and late 子时.
            if calculate_chart(birth)["四柱"] == pillars:
                matches.add(birth.isoformat(sep=" "))
    return tuple(sorted(matches, reverse=True))


@lru_cache(maxsize=512)
def lunar_months(year: int) -> tuple[tuple[int, int], ...]:
    """Real months in order, with negative codes for leap months and actual lengths."""
    if type(year) is not int or not 1 <= year <= 9999:
        raise ValueError("请填写有效的农历年份。")
    return tuple((month.getMonth(), month.getDayCount())
                 for month in LunarYear.fromYear(year).getMonthsInYear())


def calculate_lunar_chart(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int = 0,
    *,
    is_leap_month: bool = False,
    sect: int = 2,
) -> dict[str, object]:
    """Accept a lunar date; in lunar-python, a negative month number means leap month."""
    if type(month) is not int or not 1 <= month <= 12:
        raise ValueError("请先选择农历月份。")
    signed_month = -month if is_leap_month else month
    months = dict(lunar_months(year))
    if signed_month not in months:
        leap = next((-code for code in months if code < 0), None)
        hint = f"该年闰{leap}月。" if leap else "该年没有闰月。"
        raise ValueError(f"{year}年不存在所选的闰{month}月，{hint}请重新选择月份。")
    maximum = months[signed_month]
    if type(day) is not int or not 1 <= day <= maximum:
        label = ("闰" if is_leap_month else "") + str(month) + "月"
        raise ValueError(f"{year}年农历{label}只有{maximum}天，请重新选择出生日期。")
    try:
        lunar = Lunar.fromYmdHms(year, signed_month, day, hour, minute, second)
    except Exception as error:
        raise ValueError(f"无效的农历出生日期或时间：{error}") from error
    solar = lunar.getSolar()
    chart = calculate_chart(
        datetime(
            solar.getYear(),
            solar.getMonth(),
            solar.getDay(),
            solar.getHour(),
            solar.getMinute(),
            solar.getSecond(),
        ),
        sect=sect,
        time_basis="农历生日换算得到的公历时刻",
    )
    chart["输入历法"] = "农历"
    chart["输入农历日期"] = lunar.toString()
    return chart


def equation_of_time_minutes(utc_time: datetime) -> float:
    """NOAA 简化公式：返回真太阳时与平太阳时之差（分钟）。"""
    if utc_time.utcoffset() is None:
        raise ValueError("均时差计算需要带时区的时间点")
    utc_time = utc_time.astimezone(timezone.utc)
    year_length = 366 if _is_leap_year(utc_time.year) else 365
    hour = utc_time.hour + utc_time.minute / 60 + utc_time.second / 3600
    gamma = 2 * math.pi / year_length * (utc_time.timetuple().tm_yday - 1 + (hour - 12) / 24)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def convert_to_true_solar_time(
    local_time: datetime, longitude: float, timezone_name: str, fold: int | None = None
) -> tuple[datetime, float, float]:
    """返回(真太阳时, UTC偏移小时, 均时差分钟)，经度东经为正。"""
    if local_time.tzinfo is not None:
        raise ValueError("出生时间请传当地钟表时间，不要附带 UTC 偏移")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("经度范围应为 -180 到 180 度；东经填正数，西经填负数")
    if fold not in (None, 0, 1):
        raise ValueError("fold 只能是 0 或 1")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"找不到时区 {timezone_name!r}；请使用 IANA 名称，例如 Asia/Shanghai") from error

    # 夏令时回拨时，一个本地钟表时间会出现两次；让使用者明确选择其中一次。
    first = local_time.replace(tzinfo=zone, fold=0)
    second = local_time.replace(tzinfo=zone, fold=1)
    first_round_trip = first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
    second_round_trip = second.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
    first_is_valid = first_round_trip == local_time
    second_is_valid = second_round_trip == local_time
    if not first_is_valid and not second_is_valid:
        raise ValueError("这个本地时间因夏令时跳时而不存在，请核对出生时间")
    ambiguous = first_is_valid and second_is_valid and first.utcoffset() != second.utcoffset()
    if ambiguous and fold is None:
        raise ValueError("这个本地时间因夏令时回拨出现两次，请加 --fold 0 或 --fold 1")
    aware = local_time.replace(tzinfo=zone, fold=fold or 0)

    # 做一次最终往返校验，防止时区数据中的其他异常被静默接受。
    round_trip = aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
    if round_trip != local_time:
        raise ValueError("这个本地时间因夏令时跳时而不存在，请核对出生时间")

    utc_time = aware.astimezone(timezone.utc)
    offset = aware.utcoffset()
    assert offset is not None
    utc_offset_hours = offset.total_seconds() / 3600
    equation_minutes = equation_of_time_minutes(utc_time)

    # NOAA: 真太阳时分钟 = 民用钟表分钟 + 均时差 + 4*经度 - 60*UTC偏移。
    civil_minutes = local_time.hour * 60 + local_time.minute + local_time.second / 60
    correction_minutes = equation_minutes + 4 * longitude - 60 * utc_offset_hours
    true_solar_minutes = civil_minutes + correction_minutes
    true_solar_time = local_time.replace(hour=0, minute=0, second=0, microsecond=0)
    true_solar_time += timedelta(minutes=true_solar_minutes)
    return true_solar_time, utc_offset_hours, equation_minutes


def main() -> None:
    parser = argparse.ArgumentParser(description="计算出生时间对应的年、月、日、时四柱")
    parser.add_argument("birth_time", help="公历时间，格式 YYYY-MM-DD HH:MM[:SS]")
    parser.add_argument(
        "--sect",
        type=int,
        choices=(1, 2),
        default=2,
        help="日柱换日规则：1 或 2；默认 2（库的默认值）",
    )
    parser.add_argument("--longitude", type=float, help="出生地经度，东经为正、西经为负")
    parser.add_argument("--timezone", help="出生地 IANA 时区，例如 Asia/Shanghai 或 America/Los_Angeles")
    parser.add_argument("--fold", type=int, choices=(0, 1), help="夏令时回拨重叠时刻选第一次(0)或第二次(1)")
    args = parser.parse_args()
    try:
        parsed = datetime.fromisoformat(args.birth_time)
        if (args.longitude is None) != (args.timezone is None):
            raise ValueError("要做真太阳时修正，请同时填写 --longitude 和 --timezone")
        chart = calculate_chart(parsed, args.sect)
        corrected = None
        if args.longitude is not None and args.timezone is not None:
            solar_time, utc_offset, equation = convert_to_true_solar_time(
                parsed, args.longitude, args.timezone, args.fold
            )
            corrected = (
                solar_time,
                calculate_chart(
                    solar_time,
                    args.sect,
                    time_basis="真太阳时修正后的公历时刻",
                ),
                utc_offset,
                equation,
            )
    except ValueError as error:
        parser.error(str(error))

    print(f"公历：{chart['公历']}")
    print(f"农历：{chart['农历']}")
    print("四柱：")
    for name, pillar in chart["四柱"].items():
        print(f"  {name}：{pillar}")
    print(f"日柱换日规则：{chart['日柱换日规则']}")
    print(f"时间说明：{chart['时间说明']}")
    if corrected:
        solar_time, solar_chart, utc_offset, equation = corrected
        print("\n真太阳时修正：")
        print(f"  出生地时区：{args.timezone}（该日期 UTC 偏移 {utc_offset:+g} 小时）")
        print(f"  经度：{args.longitude:+g}°")
        print(f"  均时差：{equation:+.2f} 分钟")
        print(f"  修正后时间：{solar_time:%Y-%m-%d %H:%M:%S}")
        print("  修正后四柱：")
        for name, pillar in solar_chart["四柱"].items():
            print(f"    {name}：{pillar}")
        print("  注：均时差采用 NOAA 的简化公式估算。")


if __name__ == "__main__":
    main()
