# 用四本古籍做原文检索

## 先准备文本

运行 `python rag.py ingest` 会检查 `data/source/` 中的四本书；缺少时会下载项目配置的公开电子文本，再建立本地索引。需要联网（如果四本文本都已在本地，重新建索引不需要下载文本）。目前包含《穷通宝鉴》《三命通会》《子平真诠》《滴天髓》。版本来源、转录情况和注意事项见 [`data/source/SOURCE.md`](../data/source/SOURCE.md)。这些电子文本不一定是最新点校版。

如果你有更想使用的版本，把纯文本放到 `data/source/`，程序检测到本地 `.txt` 文件后就会使用本地文件，不会下载默认文本。建议保留原书的章节标题和段落空行，并在文件开头记录版本和出处：

```text
# 书名：《穷通宝鉴》
# 版本：填写版本或整理者
# 卷/章节：填写卷名或章节名
# 页码：填写页码范围（如适用）

这里开始是正文……
```

程序会把 `#` 开头的行当作出处说明，其余内容作为正文。没有来源说明时，会显示文件名和“未填写”提示，不会伪造卷名或页码。

## 安装

在项目目录打开终端，创建虚拟环境并安装依赖：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

首次运行会下载中文语义向量模型 `BAAI/bge-small-zh-v1.5`，需要网络连接。模型、下载文本和向量索引保存在 D 盘项目目录；`chroma_db/` 不提交到 Git。项目规则要求其他模型、依赖或大文件也优先保存在 D 盘。

## 建立索引和检索

```powershell
python rag.py ingest
python rag.py search "某个你想在原文中查找的问题"
```

索引阶段按完整原文段落建立记录，不按固定字数切开句子；段落跨物理行时会合并，出处保留起止行号。空行、篇章标题和句末标点用于识别段落边界。古籍不同版本的排版可能不同，换版本后应重新检查段落结构和出处。修改文本或切分规则后，运行 `python rag.py ingest` 重建段落索引。《穷通宝鉴》使用篇章与人工整理条件检索；其他三本目前按书名隔离后做语义检索，每本返回一条原文记录，适用条件尚未结构化核定。

单独修改一本书时，可运行 `python rag.py ingest --book 子平真诠`，只替换该书的索引记录。《子平真诠》当前底本的目录不参与索引；正文缺失的篇名由 `data/annotations/ziping_chapters.json` 中的精确起句定位，篇名作为整理元数据保留。更换底本需重新核对这些起句。

通用检索仍可用于找原文。新增的命盘检索会先按已整理的日主、月令、透干/藏干条件筛选，再在候选原文中按报告主题排序：

```powershell
python rag.py search-chart --topic "春木调候" --day-master 甲 --month-branch 寅 --exposed-stems 甲,丙 --hidden-stems 甲,丙,戊
```

条件标注保存在 `data/annotations/conditions.json`。标注覆盖范围有限，不能代表全书已经完成结构化整理；检索结果会显示标注状态。调整原文或增加标注后，运行 `python rag.py ingest` 重建索引。

可用 `python evaluate_retrieval.py` 对 `eval/retrieval_cases.json` 里的人工相关性样例跑实际 Chroma top-k，并查看 Recall@k、Precision@k、MRR。样例规模很小，当前只是链路演示，指标不应当被理解为全书检索质量结论。

评估分层方案和运行方法见 [evaluation.md](evaluation.md)。

## RAG 的三个环节

1. **建档**：按原文完整段落建立记录，同时保留章节、文件和起止行号出处。
2. **检索**：将问题和各段文字编码为向量，找出语义相近的原文。
3. **生成**：AI 解读入口可调用 GLM-4.7-Flash，读取《子平真诠》全文和本次检索资料，按固定顺序生成解读并校验原文引用；配置见 [接入说明](glm-setup.md)。
