# 公开网站源码

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

也可直接下载 [v0.6.1 公开站点ZIP](../releases/v0.6.1/ziping-shushu-public-v0.6.1.zip)。仅部署白名单包，数据库和运行数据放独立持久目录；配置方法见 [部署说明](../deploy/public-site/README.md)，防刷与资源限制见 [安全说明](security.md)。对应站点代码已在维护环境完成Docker构建、HTTPS和WebSocket连接检查；未执行自动化测试、真实模型生成或并发压测。此次GitHub发布本身不操作云端实例。
