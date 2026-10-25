"""Pure period labels shared by browser and Android workflows."""
PERIOD_LABELS = {"annual": "年", "monthly": "月", "daily": "日"}


def period_scope(transit):
    cycle, year = transit["大运"], transit["流年"]
    text = (f"大运{cycle['干支'] or '未起运'}（{cycle['起始年']}—{cycle['结束年']}年） · "
            f"流年{year['年份']}年 {year['干支']}")
    if "流月" in transit:
        month = transit["流月"]
        text += f" · 流月{month['名称']} {month['干支']}（{month['起始时刻'][:10]}至{month['结束时刻'][:10]}）"
    if "流日" in transit:
        day = transit["流日"]
        text += f" · 流日{day['日期']} {day['干支']}"
    return text
