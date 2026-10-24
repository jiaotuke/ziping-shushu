# 子平术数 · 公开站点部署包

这是待部署源码，不是已运行的云端服务。只包含客户端和代理端；本机后台、账本、管理员账号、作者模型密钥及演示数据均不在包内。

## 当前部署选择

当前程序是有 WebSocket 会话的 Streamlit 网页，并用本机 SQLite 保存公开站点资料。本方案部署到单台 Linux 云主机，使用 Docker Compose 和持久卷，HTTPS 使用 Caddy。先用单实例，不要直接扩为多副本共享数据库。

现有华为云事件函数不能把此包当作 `index.handler` 上传。华为云 HTTP 函数虽已支持 WebSocket，但连接受执行超时限制，临时盘也会随实例回收。仅使用云函数需要另行设计会话恢复和持久数据库；不能照搬这个部署方案。

## 资源准备

1. Linux 云主机、可用公网 IPv4。初步可从2核2GB开始；这是部署起点，未做容量测试，实际并发需观察。
2. SSH 登录权限。主账号密码、验证码和模型密钥不要发到聊天里；使用控制台或本机保存的 SSH 密钥。
3. 对外发布前准备域名、DNS 与 HTTPS；按实际地域和业务确认网站接入要求。中国大陆华为云域名建站需按官方要求办理备案。
4. 服务器安装 Docker Engine 和 Compose v2。请按所用系统的官方文档安装，不在本地 Windows 电脑下载容器镜像。
5. 云安全组只对公众开放 TCP80/443；SSH22仅对维护者地址开放。8501、8503不向公网开放。

## 尚无域名：先私下验收

上传并解压本包到服务器，例如 `/opt/ziping/releases/本次版本`。在解压目录运行：

```sh
docker compose up -d --build web
docker compose logs --tail=50 web
```

此时8501只监听服务器回环地址，不是公开网址。在你的电脑另开终端：

```powershell
ssh -L 18501:127.0.0.1:8501 登录用户@服务器IP
```

保持终端连接，再访问 `http://127.0.0.1:18501/`。不要用未加密的公网HTTP地址填写用户密码或模型密钥。

## 已有域名：正式打开 HTTPS

1. 将域名 A 记录指向服务器公网IP；已有 AAAA 记录时也要指向正确可用的服务器。
2. 将 `.env.example` 复制为 `.env`，把 `SITE_HOST` 改为真实域名，如 `bazi.example.com`，不带协议、路径或端口。
3. 版本标签 `ZIPING_RELEASE` 设为本包目录名。确认部署资源、域名与对外开放授权后运行：

```sh
docker compose --profile https up -d --build
docker compose logs --tail=50 gateway
```

Caddy通过80/443申请域名证书。证书成功后才用 `https://你的域名` 访问。程序保留默认 CORS/XSRF 保护，没有为上线禁用它们。

## 代理资料交换

真实站点初始没有代理或咨询。先在你自己的本机后台创建代理，并在「网站设置」填写实际HTTPS网址，再导出私有的网站资料包。通过维护者SSH通道上传包后：

```sh
docker compose cp /维护目录/website-live.private.json web:/tmp/website-live.private.json
docker compose exec -T web python referral_site_sync.py apply /tmp/website-live.private.json
```

导出用户咨询供你在本机核对：

```sh
docker compose exec -T web python referral_site_sync.py export-leads /var/lib/ziping/leads.json
docker compose cp web:/var/lib/ziping/leads.json ./leads.json
```

下载到自己的电脑后，在本机后台接收。确认成交和调级后重新发布。代理密码哈希文件也是私有维护资料，不要放到公开网页或Git仓库。

## 数据备份与版本更新

数据库与运行数据在固定持久卷 `ziping-public-data` 内。替换源码目录或重建容器不会自动迁移、删除或备份此卷。

```sh
docker compose exec -T web python maintenance/backup_public.py
docker compose cp web:/var/lib/ziping/backups ./backups
```

将备份复制到另一台可信设备，不能只留在同一服务器。恢复前停止站点并核对备份，再由维护者操作；不要把旧副本直接覆盖正在使用的数据库。

更新前先备份，使用新版本标签构建；上线后验收，保留旧版本目录和镜像以便回滚。不要执行 `docker compose down -v`，该选项会删除持久卷。重启会中断网页会话，先让用户下载报告；长报告进度目前只保存在会话内。

## 发布边界

此包没有镜像构建、运行验收或并发压测的通过记录。当前开发电脑没有Docker，未安装或下载大体积容器依赖；依赖与镜像应在所选云主机上构建。首次公网开放前需要完成基础页面、代理改密、数据持久化、模型会话隔离和备份恢复验收，并配置流量/滥用防护。

参考：[Streamlit Docker部署](https://docs.streamlit.io/deploy/tutorials/docker)、[华为云WebSocket](https://support.huaweicloud.com/usermanual-functiongraph/functiongraph_01_1885.html)、[华为云存储选型](https://support.huaweicloud.com/productdesc-functiongraph/functiongraph_02_1002.html)、[华为云备案限制](https://support.huaweicloud.com/intl/zh-cn/icprb-icp/icp_01_0008.html)、[Docker持久卷](https://docs.docker.com/engine/storage/volumes/)、[Caddy反向代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)。
