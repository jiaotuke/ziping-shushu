# 子平术数 · Ziping Shushu

**在线使用：[子平术数 · jiaotuke.online](https://jiaotuke.online/)**

直接用浏览器访问，无需下载安装。

当前版本 **v0.7.0（2026-10-25）**。支持公历、农历、四柱排盘，智谱 / DeepSeek / 书生·端砚自备密钥解读，原文检索及 HTML/TXT/JSON 报告。

- 原局报告先生成，前六步正式大运逐步保存，包含运内逐年趋势、解释性评分与交互子平K线；每段完成后可以暂停和继续。
- 完成基础报告后，可反复选择**仅分析年、仅分析月、仅分析日**。专项报告只输出对应层级，不重复附带基础报告。
- 第三档可导入以前下载的JSON、HTML、TXT基础报告（最大2MB），核对出生资料与性别后直接追加专项。旧文本没有保存的评分不会补造。
- 报告记录性别、出生时刻，文件名使用四柱及报告范围。四柱输入自动反查日期，有多个结果再选择，时刻采用对应时柱默认值。
- 增加天干生克、刑的方向、半会/拱会和暗合规则说明，以及《千里命稿》关系条件检索模块。大运阶段根据每步大运及运内各年引动关系重新检索、去重，保存实际引用材料与覆盖记录。

代码规则识别干支关系；古籍提供候选依据，模型仍需判断条件。字面引用通过不代表解释正确，解释性评分也不是客观事件概率。

人工解读参考价：原局18.88元，原局＋大运36.88元；在基础上追加所选年/月/日，各2元/项。通过微信沟通，网站不自动扣费。自备模型只按所用平台收费。

## 下载与运行

- [v0.7.0 公开网站源码ZIP](releases/v0.7.0/ziping-shushu-public-v0.7.0.zip)
- [发布说明](docs/releases/v0.7.0.md)、[安卓安装与构建](docs/install-packages.md)、[检索规则](docs/qianli-retrieval.md)
- [Skill v0.6.0](releases/v0.6.0/ziping-shushu-skill-v0.6.0.zip) 保持原版，本次未修改。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-public.txt
.venv\Scripts\python -m streamlit run public_app.py --server.address=127.0.0.1
```

公开源码包不附带《千里命稿》完整电子转录，原转录的具体底本与分发许可尚待核验。未提供该书时仍可使用其他四书；该书模块不会伪造引文。自行取得适用权限的兼容底本后，放入 `data/source/千里命稿.txt`，核对章节和原文行锚点后启用。不同版本不可直接共用锚点。其他底本来源与状态见 [SOURCE](data/source/SOURCE.md)。项目代码许可不自动覆盖电子底本。

安卓本地版本已重新构建为0.7.0；独立进行排盘及古籍检索，模型解读需要联网与用户自己的API Key。APK单独交付，不放入源码ZIP。没有进行真实手机验收、自动化测试、模型生成或负载压测。云部署使用Docker/Caddy和持久卷，见[部署说明](deploy/public-site/README.md)。
