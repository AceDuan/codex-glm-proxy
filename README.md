# codex-glm-proxy

将 Codex CLI 使用的 OpenAI Responses API 转换为智谱 Anthropic Messages API。

```text
Codex CLI
  → http://127.0.0.1:8765/v1/responses
  → https://open.bigmodel.cn/api/anthropic/v1/messages
```

## 当前支持

- Responses 文本输入和 Anthropic 文本流式输出。
- 函数工具、工具参数流和工具结果续接。
- `namespace` 工具展开为普通函数。
- Token usage 和上游 HTTP 错误转换。
- `GET /healthz` 和 `GET /v1/models`。

首版会过滤没有直接等价能力的 `web_search` 和 `image_generation` 工具，不实现 `/v1/responses/compact`。

## 安装

本项目的 Python 操作统一通过 `misc-run` 执行：

```bash
misc-run codex-glm-proxy -- \
  python -m pip install --no-build-isolation -e .
```

## 启动

后台启动（推荐）：

```bash
misc-run codex-glm-proxy -- \
  codex-glm-proxy start
```

状态和停止：

```bash
misc-run codex-glm-proxy -- codex-glm-proxy status
misc-run codex-glm-proxy -- codex-glm-proxy stop
```

PID 和日志默认保存到：

```text
~/.codex-glm/proxy/proxy.pid
~/.codex-glm/proxy/proxy.log
```

前台启动：

```bash
misc-run codex-glm-proxy -- \
  codex-glm-proxy serve
```

默认监听：

```text
http://127.0.0.1:8765
```

健康检查：

```bash
misc-run codex-glm-proxy -- \
  codex-glm-proxy health
```

## Codex 配置

自定义 provider 指向本地代理：

```toml
model_provider = "custom"
model = "glm-5.2"
model_reasoning_effort = "medium"
disable_response_storage = true

[model_providers.custom]
name = "zhipu_glm"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"
env_key = "ZHIPU_API_KEY"
```

代理从 Codex 请求的 Bearer 认证头中取得 API Key，只在当前上游请求中转发给智谱，不写入日志或文件。

## 测试

```bash
misc-run codex-glm-proxy -- \
  env PYTHONPATH=src python -m unittest discover -s tests -v
```

## 参考

协议转换设计参考了 MIT 许可的 [cc-switch](https://github.com/farion1231/cc-switch) Responses/Anthropic 转换模块，但本项目采用独立的 Python 标准库实现。
