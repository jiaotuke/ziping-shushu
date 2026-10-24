# 命令与数据口径

`scripts/ziping.py` 的 stdout 是 UTF-8 JSON，运行不产生模型请求。基础命令默认不保存出生信息或报告；使用 `--output` 时写入指定新文件，不覆盖已有文件。显式大运工作流会在指定workdir中保存私有进度，并在导出时生成报告。

## chart / prepare

两者共享以下参数：

| 参数 | 用途 |
| --- | --- |
| `--birth "YYYY-MM-DD HH:MM[:SS]"` | 公历或农历年月日时分秒，必须明确历法 |
| `--calendar solar/lunar` | 默认 solar；农历日期按农历规则校验，不用公历限制套用 |
| `--leap-month` | 只用于农历闰月 |
| `--pillars "年柱 月柱 日柱 时柱"` | 与 birth 二选一，也可用逗号分隔 |
| `--matched-date "YYYY-MM-DD HH:MM:SS"` | 四柱反查多个候选后，选取返回列表中的完整日期时刻 |
| `--longitude 116.4 --timezone Asia/Shanghai` | 同时提供才启用真太阳时修正，纬度不参与此公式 |
| `--fold 0/1` | 夏令时回拨时选择第一次或第二次时刻 |
| `--luck --gender 男/女` | 计算前六步大运摘要；起运 sect=1，排盘 sect=2，与项目默认口径一致 |
| `--output "目标.json"` | 可选；写新文件，路径由使用者指定 |

`chart` 返回四柱、详细十神、神煞、干支关系及日期匹配状态。`prepare` 另外执行四本古籍的独立检索，返回可供当前 AI 解读的来源资料。

`prepare` 支持 `--context focused/full`、`--sources-per-book`（默认2，范围1～20）、`--chars-per-book`（默认2400，范围400～20000）。focused 按完整段落选择，不截断引用；full 不限制《子平真诠》段落数及全文字数，其他三书仍按上述预算。检索展开的篇章仅用于定位；没有送给 AI 的内容不能宣称已读。

## 日期状态

- `resolved`：有输入公历/农历日期或唯一匹配日期。
- `choose_date`：四柱反查有多个候选，`matching_dates` 列出可选日期；原局仍可分析，大运等待用户选择。
- `no_match`：反查范围1800年至当前日期没有结果，保留原四柱，不产生起运数据。

无论哪种状态，都不能为了得到起运数据而自行挑选候选日期。时柱默认时刻沿用现有 `find_pillar_birth_times`，包括晚子时和交节边界的库匹配结果。

## search / source

`search --query "问题" [--book "书名"] [--count 2] [--chars-per-book 2400]` 在指定书内做段落 BM25 检索；省略 book 会分别检索四书。只返回完整段落及真实出处，低相关度不代表有效证据。count 范围1～20。

`source --id SOURCE_ID [--id SOURCE_ID]` 读取先前返回的真实来源记录，补齐完整上下文；不存在的编号报错。它不读取任意文件路径。

## 返回约定

成功返回 `ok: true`；参数或数据错误返回 `ok: false` 和可读 `error`，退出码2。`source_notes` 汇报缺书、缺少完整段落及预算导致的省略。

## 显式大运分析命令

`luck-start` 复用chart出生输入，必须提供性别、`--confirm-extended`、`--request`和技能目录外的`--workdir`。确定范围后传重复的`--cycle`或`--first-six`；不传范围只列选项。其他三个阶段命令为`luck-stage`、`luck-accept --stage-id --response`、`luck-render [--outdir]`，均需指定workdir，且不会调用模型API。精确流程和门控规则见 [luck-workflow.md](luck-workflow.md)。

## 本地安装

技能目录可整体复制给其他支持 Agent Skills 的工具。安装依赖时将 pip 缓存放项目盘，例如 Windows：

```powershell
$env:PIP_CACHE_DIR = 'D:\ai bazi\.cache\pip'
python -m pip install -r '<skill>\requirements.txt'
```

代码和书籍是随包快照。项目维护者修改核心模块后，可运行项目里的 `tools/prepare_ziping_skill.py` 更新快照并重新生成白名单 ZIP；它不会上传云端、操作数据库或下载依赖。
