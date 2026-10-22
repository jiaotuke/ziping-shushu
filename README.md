# 子平术数 · Ziping Shushu

本项目结合八字排盘、四本古籍的独立检索，以及智谱 / DeepSeek 模型的八步 AI 解读。

## 从新副本启动

建议将项目克隆到 D 盘。仓库包含源码、四本固定古籍底本、篇章及条件标注、文档和测试；虚拟环境、模型缓存、向量索引和真实 API Key 不随仓库上传。

在 D 盘项目目录打开 Windows PowerShell（Python 3.10 或更高）：

```powershell
$projectRoot = (Get-Location).Path
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.cache/pip'
$env:HF_HOME = Join-Path $projectRoot '.cache/huggingface'
$env:SENTENCE_TRANSFORMERS_HOME = Join-Path $projectRoot '.cache/sentence-transformers'
$env:TRANSFORMERS_CACHE = Join-Path $projectRoot '.cache/transformers'
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe rag.py ingest
.\.venv\Scripts\python.exe -m streamlit run app.py
```

首次安装及下载向量模型需要联网；之后可复用项目缓存。启动后访问 `http://127.0.0.1:8501/`。AI 解读需在网页填写对应平台密钥，或按 [模型接入说明](docs/glm-setup.md) 配置本地 secrets 文件。

当前古籍电子转录文本的来源与版本记录见 [SOURCE.md](data/source/SOURCE.md)。

## 当前功能

- `rag.py ingest`：按完整原文段落建立四本古籍的本地向量索引，并为每段保存书名、篇章和出处。
- `rag.py search "问题"`：检索相关原文。
- 《滴天髓》只索引甲至癸十干专论，按命盘日干精确返回对应文章，正文、原注与任氏注分段展示。
- `rag.py search-chart ...`：针对《穷通宝鉴》按日主篇章和月令条件筛选，再按报告主题排序原文。
- `evaluate_retrieval.py`：用人工标注的案例评估检索 top-k。
- `bazi.py "1990-01-01 12:00"`：根据公历出生时间计算四柱。
- `bazi.calculate_lunar_chart(...)`：代码接口支持农历日期及闰月标记。
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

Streamlit 启动后会在浏览器打开本机地址（通常是 `http://localhost:8501`）。中国行政区列表按需从 DataV.GeoAtlas 加载并缓存在项目 `.cache/china_admin/`；选中县区后用其中心坐标修正真太阳时。目前仍是本机网页，尚未部署云端，AI 解读需配置所选平台的 API Key，设置步骤见 [模型接入说明](docs/glm-setup.md)。

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
