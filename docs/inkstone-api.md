# 书生·端砚模型接入

子平术数的“自备模型”和“古籍译文”支持选择“书生·端砚”。

1. 在端砚“科研模型 → API Key”创建并自行保存完整密钥。
2. 在子平术数选择“书生·端砚”，填入该平台的密钥。
3. 选择生成模型，例如 `intern-s2`；也可从端砚模型列表复制 ID，选择“自定义模型 ID”并填写对应的真实上下文窗口。
4. 点击“检查密钥与模型”读取 `GET /v1/models`，按端砚文档不扣墨点。它核对密钥和模型可见性，不生成报告；确认后再按需生成报告或译文。

API 基础地址为 `https://discovery-api.intern-ai.org.cn/v1`，实际文本生成请求为 `POST /v1/chat/completions`，鉴权使用 `Authorization: Bearer <TOKENPLAN_API_KEY>`。请求示例仅说明格式，不会自动执行：

```json
{
  "model": "intern-s2",
  "messages": [{"role": "user", "content": "你好"}],
  "max_tokens": 1024,
  "stream": false
}
```

当前按照端砚公开文档使用基础 OpenAI Chat Completions 协议，不发送智谱或 DeepSeek 的专有思考参数、JSON 模式和采样设置。模型采用平台默认推理方式；报告仍有 JSON 内容要求、格式及原文引用校验。不保证所有模型首次生成都能通过内容校验。

预置模型 ID 和窗口来自 2026-10-25 查阅的官方模型表，可能随平台调整；以登录后的可用模型为准。`intern-decision-4b` 等决策模型只支持 SystemOne，不用于本项目的报告生成。

三个平台的会话密钥独立保存。公开网站只使用访问者自己的密钥，不读取作者环境变量或本机 secrets。作者本地工作台可配置环境变量 `TOKENPLAN_API_KEY`，不要将真实密钥写进文档、源码或公开包。

官方资料：

- [端砚科研模型及使用文档](https://discovery.intern-ai.org.cn/token-plan/home?tabIndex=3)
- [Chat Completions API](https://cdn-static.openxlab.org.cn/magic-maker/action-static/tokenplan-doc/api-reference/03-chat-completions.md)
- [模型列表与计费](https://cdn-static.openxlab.org.cn/magic-maker/action-static/tokenplan-doc/quick-start/04-model-limits-and-pricing.md)

## HTTP 429 的处理

端砚的 Chat Completions 接口使用英文错误码区分两种情况：`rate_limit_exceeded` 是调用限流，`quota_exceeded` 是可用墨点不足。余额或周期额度剩余99%也不能单独排除 RPM/TPM 限流；同一账户的多个 API Key 共用限制。

程序仅显示官方错误码白名单、固定中文解释，以及符合格式的 `req_` 请求追踪编号；不显示上游原始错误正文、请求内容或密钥。平台未返回可识别错误码时，明确说明无法仅凭429判断原因。

HTTP429不自动重试，不切换模型、不自动补充额度；已经完成的报告阶段保留。先暂停调用，检查平台限额及调用记录，再自行决定是否重试。出现持续失败可向平台提供请求编号、调用时间和模型 ID，不能提供完整密钥。

参考：[端砚错误码](https://cdn-static.openxlab.org.cn/magic-maker/action-static/tokenplan-doc/quick-start/06-error-codes.md)、[限速说明](https://cdn-static.openxlab.org.cn/magic-maker/action-static/tokenplan-doc/quick-start/05-rate-limits.md)。
