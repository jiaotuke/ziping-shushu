# 公开网站源码

本仓库提供客户端、代理登录查询和维护者主动文件交换工具；作者的本机管理系统及启动器不公开。仓库和下载包不含真实代理账号、咨询、成交记录、密码哈希或模型密钥。启动新副本不会自动出现作者的业务数据。

推荐使用轻量依赖启动公开站点：

```powershell
# 先进入解压后的项目目录，创建虚拟环境；本项目缓存优先放D盘。
$env:PIP_CACHE_DIR = Join-Path (Get-Location).Path '.cache/pip'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-public.txt
.\.venv\Scripts\python.exe -m streamlit run public_app.py --server.address=127.0.0.1 --server.port=8502
```

浏览器访问 `http://127.0.0.1:8502/`。公开模式使用段落/BM25检索，不下载大型向量模型；解读与译文使用访问者自己填写的模型密钥，不回退到作者环境或 secrets 中的密钥。

客户登记咨询后取得编号和微信备注，代理查看维护者发布的查询资料；成交与佣金以维护者审核为准。实际代理账号和咨询文件须通过可信维护通道传输，不能放进Git或公开下载目录。`referral_site_sync.py`是部署终端文件交换工具，不是公网管理接口。

生成部署源码包：

```powershell
.\.venv\Scripts\python.exe tools/prepare_cloud_release.py
```

也可直接下载 [v0.6.0 公开站点ZIP](../releases/v0.6.0/ziping-shushu-public-v0.6.0.zip)。仅部署白名单包，数据库和运行数据放独立持久目录；配置方法见 [部署说明](../deploy/public-site/README.md)。这次GitHub更新没有操作现有云端实例，也没有提供本版Docker构建或公网验收通过记录。
