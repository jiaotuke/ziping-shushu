# 子平术数公开站点

本包包含客户与代理网站源码。使用 Linux、Docker Compose 和 Caddy，网站通过 WebSocket 保持 Streamlit 会话，SQLite 放在持久卷。

1. 准备域名，将 A 记录指向服务器；公网只开放 HTTP 80 和 HTTPS 443，维护入口使用密钥。
2. 将 `.env.example` 复制为 `.env`，填写 SITE_HOST 与 ZIPING_RELEASE。
3. 运行 `docker compose --profile https up -d --build`，检查容器健康和 HTTPS。
4. `site_data` 卷保存网站运行数据，更新时不要删除。更新前使用 `maintenance/backup_public.py` 进行 SQLite 一致性备份。

先构建新镜像，再在没有报告生成时更新服务。切换会影响当前网页会话，下载报告后再刷新。保留旧镜像、旧源码和数据库备份以便回滚。禁止将运行数据库、模型密钥、SSH配置或签名材料加入源码包。

公开源码包不附带《千里命稿》完整电子转录。相关来源和底本要求见 `site/data/source/SOURCE.md`；需自行确认使用权限并放入兼容底本，才能启用该书检索。不要用其他版本替换后沿用未经验证的章节锚点。
