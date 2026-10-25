# 子平术数 · Ziping Shushu

本项目结合八字排盘、四本古籍的独立检索，以及智谱 / DeepSeek / 书生·端砚模型的八步 AI 解读。

当前公开源码版本为 **v0.6.1（2026-10-25）**，增加书生·端砚接入、明确的限流错误诊断，以及公开站点防刷、生成并发和资源限制。下载：[公开网站源码 ZIP](releases/v0.6.1/ziping-shushu-public-v0.6.1.zip)；[完整 Skill ZIP](releases/v0.6.0/ziping-shushu-skill-v0.6.0.zip) 保持v0.6.0原版，不在本次更新。见 [Skill 使用说明](docs/agent-skill.md)、[端砚接入说明](docs/inkstone-api.md) 和 [本版发布说明](docs/releases/v0.6.1.md)。本次没有重新构建 EXE/APK，已有预构建安装包仍为 v0.5.0。

第五版 0.5.0 采用“先看结果”的报告布局：顶部是真实绘制的可点击子平 K 线，选择大运后显示白话总评，以及事业与学业、财务与资源、感情与合作三项卡片；完整推导与古籍依据默认折叠。健康和心境不新增。HTML 下载报告也可离线点击切换，打印包含全部已分析大运。详见 [第五版报告布局](docs/v5-report-ui.md)。Windows ZIP 与安卓 APK 使用 0.5.0 源码重新构建；构建产物与源码分开交付。

网页版岁运分析：第二、第三档覆盖起运后的前六步正式大运，分述好坏、事业、财务、感情，给出解释性评分，并由代码绘制子平 K 线；合冲刑害逐条说明可能现实表现与条件。所选流年及可选月日另外详解，分别共 8 / 10 个基础请求阶段。内容或格式失败每段自动修正一次，修正另计模型用量；仍失败保留草稿暂停。长报告分段生成、保留会话进度。评分权重是项目规则，不是古籍自带数值。详见 [评分、K线与生成流程](docs/luck-analysis.md)。

原文引用现为可选：有适用原文再显示，没有时标为“模型推演”，不会因缺少引用中断报告；无法核对的摘录省略。安装包复用同一套分析、草稿恢复及报告渲染逻辑。

## Windows 与安卓安装包

新增 Windows EXE 便携包与可独立运行的安卓 APK 构建。使用者无需安装 Python；排盘、岁运及古籍在设备本地运行，AI 解读和译文仍需要联网与用户自己的模型密钥。安装包的候选段落使用关键词排序，不附带大型向量模型。安装方法、功能差异及构建边界见 [安装包说明](docs/install-packages.md)。本次仓库更新包含源码与构建脚本；预构建 ZIP/APK 需在 Releases 单独发布，不包含在「Download ZIP」源码压缩包中。

## 本次更新 · 2026-10-25

v0.6.1 保留结果优先布局、三方面卡片、交互 K 线、十年详解、客户／代理入口切换和四柱匹配日期，补充第三个模型平台及站点安全控制。Skill 默认只做排盘及基础解读；用户明确要求十年大运分析或 K 线时，才运行指定范围的分阶段评分流程。完整修改与检查范围见 [更新记录](CHANGELOG.md)；站点限制见 [安全说明](docs/security.md)。

## 从新副本启动

对外入口为 `public_app.py`，包含客户功能与代理登录查询。**本机管理系统、启动器及全部业务资料不在本公开仓库中。** 新副本没有真实代理、咨询或成交记录；代理账号由维护者私下开通和发布。准备站点使用 `tools/prepare_public_site.py` 的白名单目录，不能把整个开发目录上云。启动和资料边界见 [公开网站说明](docs/public-site.md)。旧的 `?preview=paid` 咨询入口预览保留。

不熟悉大模型 API 接入的用户，可添加作者微信 `bxzgf-bxbgf` 沟通付费解读。网站提供咨询编号、来源登记和人工成交佣金台账；不接入收款码或支付接口。自备模型生成的报告支持 HTML/TXT/JSON 下载。详见 [付费咨询入口](docs/paid-analysis-ui.md)。

建议将项目克隆到 D 盘。仓库包含源码、四本固定古籍底本、篇章及条件标注、文档和测试；虚拟环境、模型缓存、向量索引和真实 API Key 不随仓库上传。

先安装 **64 位 Python 运行时**，不能只安装启动器或安装管理器。本机开发环境为 Python 3.10；使用其他版本时，需要将下面的 `$pythonVersion` 改成实际已安装、且依赖可正常安装的版本。

新版 Python 安装管理器用 `py list` 查看已安装版本；旧版启动器用 `py -0p`。安装方式见 [Python 官方 Windows 说明](https://docs.python.org/3/using/windows.html)。

打开 Windows PowerShell，执行以下整段。**先将项目目录改成实际解压位置，不能直接在 `D:\` 根目录执行。** 如果文件夹多套了一层，以同时包含 `app.py` 和 `requirements.txt` 的目录为准。

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location -LiteralPath 'D:\ziping-shushu-main' # 改成实际项目目录
    if (!(Test-Path -LiteralPath 'app.py') -or !(Test-Path -LiteralPath 'requirements.txt')) {
        throw '当前不是项目目录：需要同时找到 app.py 和 requirements.txt。'
    }
    $projectRoot = (Get-Location).Path
    $env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache/pip'
    $env:HF_HOME = Join-Path $projectRoot '.cache/huggingface'
    $env:SENTENCE_TRANSFORMERS_HOME = Join-Path $projectRoot '.cache/sentence-transformers'
    $env:TRANSFORMERS_CACHE = Join-Path $projectRoot '.cache/transformers'

    $pythonVersion = '3.10' # 若实际安装的是 3.11，这里改成 '3.11'
    py "-$pythonVersion" --version
    if ($LASTEXITCODE -ne 0) { throw '没有找到所选 Python 运行时，请先安装或修改 pythonVersion。' }
    py "-$pythonVersion" -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '虚拟环境创建失败，已停止后续步骤。' }

    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，已停止建立索引和启动网页。' }
    .\.venv\Scripts\python.exe rag.py ingest
    if ($LASTEXITCODE -ne 0) { throw '索引建立失败，请先处理上面的错误。' }
    .\.venv\Scripts\python.exe -m streamlit run app.py
}
```

首次安装及下载向量模型需要联网；之后可复用项目缓存。启动后访问 `http://127.0.0.1:8501/`。AI 解读需在网页填写对应平台密钥，或按 [模型接入说明](docs/glm-setup.md) 配置本地 secrets 文件。

### Windows 常见安装错误

- **`No runtime installed that matches 3.10`**：当前启动器找不到 Python 3.10。先查看实际版本，安装对应运行时或修改 `$pythonVersion`；这一步成功后再创建虚拟环境。
- **找不到 `.venv\Scripts\python.exe`**：通常是虚拟环境没有创建成功，或没有进入项目目录。不要跳过前面的错误继续执行后续命令。
- **目录停在 `PS D:\>`**：需要先进入下载或解压后的项目子目录，而不是把 `.venv` 建在 D 盘根目录。

当前古籍电子转录文本的来源与版本记录见 [SOURCE.md](data/source/SOURCE.md)。

## 当前功能

- `rag.py ingest`：按完整原文段落建立四本古籍的本地向量索引，并为每段保存书名、篇章和出处。
- `rag.py search "问题"`：检索相关原文。
- 《滴天髓》只索引甲至癸十干专论，按命盘日干精确返回对应文章，正文、原注与任氏注分段展示。
- 网页《穷通宝鉴》按日干、月令直接定位对应月份的完整原文段落；合月或季节共论明确注明，不回退到“论木”“论水”等五行总论。`rag.py search-chart ...` 保留条件标注检索的命令行入口。
- `evaluate_retrieval.py`：用人工标注的案例评估检索 top-k。
- `bazi.py "1990-01-01 12:00"`：根据公历出生时间计算四柱。
- `bazi.calculate_lunar_chart(...)`：代码接口支持农历日期及闰月标记。
- `bazi.calculate_pillars_chart(...)`：直接输入年、月、日、时四柱，生成十神、藏干、纳音、空亡、星运及神煞资料；网页“出生日期与时间”提供“四柱八字”入口，可继续检索古籍和生成 AI 解读。
- 四柱排盘包含“基础排盘 / 专业细盘”。专业细盘沿用 `6tail/lunar-python` 的起运、大运与流年 API，提供按节气划分的流月、流日，支持横向滚动、左右箭头和卡片选择；需出生时刻及性别。详见 [专业细盘](docs/professional-chart.md)。
- 专业细盘按原局、大运、流年、流月、流日分层展示合、冲、刑、害、破、三合、三会、半合及拱合关系，保留参与柱位，区分各层新增与补齐；合化单独列线索、保留待核。AI 默认分析原局，也可选择结合运年或运年月日完整范围。详见 [关系计算口径](docs/pillar-relationships.md)。
- 每本古籍提供“原文 / 译文”页签；AI 译文支持独立选择平台与模型，按当前文章逐段翻译、保存进度和本地缓存，并可下载。无需先生成八字解读。详见 [AI 译文](docs/ai-translation.md)。
- `app.py`：Streamlit 本机网页，使用公历/农历日期时间输入和中国省、市、县区三级地点选择。排盘后可分别检索《穷通宝鉴》《三命通会》《子平真诠》《滴天髓》；《穷通宝鉴》使用篇章与条件检索，《三命通会》按四层线索检索，《子平真诠》按篇章线索检索，《滴天髓》按日干精确定位。AI 解读支持选择智谱与 DeepSeek 平台及模型，分别填写对应平台的 API Key 后可用。

排盘使用 GitHub 上的 [6tail/lunar-python](https://github.com/6tail/lunar-python)，而不是本项目自行重写历法。网页会显示十神、藏干、纳音和旬空；首批命局神煞根据《三命通会》卷二、卷三的明确查表规则计算，并显示取法和篇目。排盘与规则模块只标记规则命中；格局、旺衰或调候解释在独立的 AI 解读入口展示；农历日历神煞不作为命局分析结果展示。

## 运行排盘

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe bazi.py "1990-01-01 12:00"
```

靠近晚上 11 点出生时，日柱可能受换日流派影响。可以用 `--sect 1` 或 `--sect 2` 查看该库提供的两种规则；默认是 2。不填写地点参数时，程序只按输入的当地民用钟表时间排盘。

有出生地经度和时区时，可以额外计算真太阳时并显示修正后的四柱：

```powershell
.\.venv\Scripts\python.exe bazi.py "1990-01-01 12:00" --longitude 116.4 --timezone Asia/Shanghai
```

经度东经为正、西经为负。纬度不参与“时间”修正；这里需要的是经度和出生地 IANA 时区。公式和限制见 [排盘模块说明](docs/bazi-module.md)。

## 打开本机网页

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit 启动后会在浏览器打开本机地址（通常是 `http://localhost:8501`）。中国行政区列表从随项目提供的本地快照读取，首次打开及选择地区不再请求网络；中心坐标用于真太阳时修正，数据来源与覆盖范围见 [地区资料](data/regions/SOURCE.md)。古籍解析结果按文件版本缓存，源码版的向量模型延迟到实际语义查询时加载。实现与生效方式见 [启动与检索优化](docs/performance.md)。源码更新不会自动更新任何云端实例；AI 解读需配置所选平台的 API Key，设置步骤见 [模型接入说明](docs/glm-setup.md)。

## 学习资料

- [第一次 RAG：从原文到检索](docs/first-rag.md)
- [排盘模块说明](docs/bazi-module.md)
- [分层评估方案](docs/evaluation.md)
- [第一个网页：Streamlit](docs/streamlit-app.md)

## 运行自动化测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
```

检索评估需先重建索引，再运行：

```powershell
.\.venv\Scripts\python.exe rag.py ingest
.\.venv\Scripts\python.exe evaluate_retrieval.py
```
