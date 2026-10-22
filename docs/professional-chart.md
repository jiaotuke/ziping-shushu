# 专业细盘

在“四柱排盘”下切换“基础排盘 / 专业细盘”。基础排盘保留原来的四柱卡片。专业细盘将原局和选择的流年、大运、流月、流日放在同一表格中，下方四条横向选择带可触控滑动、滚轮横向滚动、点左右箭头浏览，并通过点击卡片选择。更换上层选择会更新下层范围；各层关系同步计算，AI 可选择使用当前运年或运年月日完整范围。

## 采用的 GitHub 实现

项目已安装的 `lunar_python==1.4.8` 提供所需算法，不新增模型或依赖，不复制其他排盘项目的界面代码。

| 内容 | 现成接口与来源 |
| --- | --- |
| 起运、顺逆 | `EightChar.getYun(gender, sect)`；[Yun.py](https://github.com/6tail/lunar-python/blob/master/lunar_python/eightchar/Yun.py) |
| 大运 | `Yun.getDaYun()`、`DaYun.getGanZhi()`；[DaYun.py](https://github.com/6tail/lunar-python/blob/master/lunar_python/eightchar/DaYun.py) |
| 流年 | `DaYun.getLiuNian()`；[LiuNian.py](https://github.com/6tail/lunar-python/blob/master/lunar_python/eightchar/LiuNian.py) |
| 流月 | `Lunar.getJieQiTable()` 定交节时刻，区间内部调用 `getMonthInGanZhiExact()`；[Lunar.py](https://github.com/6tail/lunar-python/blob/master/lunar_python/Lunar.py) |
| 流日 | `Solar.fromYmdHms(...).getLunar().getDayInGanZhiExact2()`；同上 |

官方 [demo.py](https://github.com/6tail/lunar-python/blob/master/demo.py) 已演示起运、大运、流年、流月调用链；[LiuYue.py](https://github.com/6tail/lunar-python/blob/master/lunar_python/eightchar/LiuYue.py) 提供十二个月的干支。页面额外需要每个节月的起止时刻和日期，因此用现成节气表与精确月柱接口生成选择项，避免把农历初一或公历每月一日作为节月边界。

## 输入及计算口径

- 性别在“开始排盘”之前选择，保存至当前命盘；库按年干阴阳和性别确定顺逆。起运固定采用按时辰折算（`sect=1`），专业细盘不再显示性别或算法设置区。起运算法与原局日柱换日的 `sect=2` 分开管理。
- 使用当前命盘的排盘时刻计算，保留已有时间修正口径；起运日期和“出生后几年几个月几天几小时”均取库返回值。
- 只输入四柱时，可在“开始排盘”之前展开“补充出生时刻（可选，用于专业细盘）”，填写公历出生日期与对应排盘时刻。补充时刻计算出的四柱必须与当前四柱一致，不能唯一反推日期后擅自选定。
- 年龄显示为库使用的虚岁口径。大运年表沿用库的年度编排，交运年份内的精确交接需结合上方交运时刻，不能将当年元旦理解为交运时刻。
- 流年使用库的干支年；流月从立春至下一年立春，按十二个“节”的精确时刻切换，不按阴历月份切换。
- 流日列表包含该节月覆盖的公历日期，交节当天可能同时出现在两个相邻节月；日柱沿用当前项目的晚子时当天规则（`Exact2`），列表展示该公历日的日柱，不提供逐时流时盘。
- 十神、藏干、星运均以原局日干为基准，自坐以各柱天干为基准。神煞只显示原局已经实现的规则结果，不将日历每日宜忌当作流动命局神煞。
- AI 默认发送原局、原局干支关系与古籍资料。可选“原局＋当前大运、流年”，或“原局＋当前运年、流月、流日”；按选择加入对应运程与起运资料，切换不会自动调用模型。完整范围会随月日选择使旧报告失效，仅运年范围不受月日变化影响。

## 干支关系

选择带下方展示原局关系、大运引动、流年引动、流月引动、流日引动，以及合化待核条件。保留具体参与柱位，区分各层新增与补齐；较细层级不回写较粗层级。五合、六合、三合、三会均不自动成化，流月不替代出生月令。完整口径、原文依据及 GitHub 工程参考见 [原局与岁运的干支关系](pillar-relationships.md)。

源码依赖采用上游 [MIT License](https://github.com/6tail/lunar-python/blob/master/LICENSE)。页面不是对参考应用算法或结果完全一致的承诺，起运及换日口径应结合实际使用方式核对。
