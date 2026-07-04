# codex-glm-proxy

将 Codex CLI 使用的 OpenAI Responses API 转换为智谱 Anthropic Messages API。

支持 Linux、WSL 和 Windows。后台进程管理会自动按运行平台选择实现：

- Linux/WSL 使用独立会话，并通过 `SIGTERM` 停止进程。
- Windows 使用无窗口的新进程组，并通过 `taskkill` 停止进程树。

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

本项目的 Python 操作统一通过 `uv` 执行。在项目根目录下：

```bash
uv sync
```

## 启动

后台启动（推荐）：

```bash
uv run codex-glm-proxy start
```

状态和停止：

```bash
uv run codex-glm-proxy status
uv run codex-glm-proxy stop
```

PID 和日志默认保存到：

```text
~/.codex-glm/proxy/proxy.pid
~/.codex-glm/proxy/proxy.log
```

前台启动：

```bash
uv run codex-glm-proxy serve
```

默认监听：

```text
http://127.0.0.1:8765
```

健康检查：

```bash
uv run codex-glm-proxy health
```

Windows 也可使用项目根目录的包装器。它会从 `UV_EXE`、`PATH` 或常见的用户级安装目录查找 `uv`：

```bat
codex-glm-proxy.cmd start
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

## 公共脚本

[`scripts`](scripts/) 提供 Windows 和 WSL 使用的 Codex 快捷命令。GLM 命令会自动启动代理，从 `~/.codex-glm/glm-api-key.json` 读取密钥，并将 `CODEX_HOME` 设置为 `~/.codex-glm`。

```json
{
  "ZHIPU_API_KEY": "你的智谱 API Key"
}
```

| 命令 | 模型 | 权限 | 搜索 |
| --- | --- | --- | --- |
| `ax` | 默认 Codex | `workspace-write` / `on-request` | 否 |
| `axs` | 默认 Codex | `workspace-write` / `on-request` | 是 |
| `axf` | 默认 Codex | `danger-full-access` / `never` | 否 |
| `axg` | GLM | `workspace-write` / `on-request` | 否 |
| `axgs` | GLM | `workspace-write` / `on-request` | 是 |
| `axgf` | GLM | `danger-full-access` / `never` | 否 |

WSL 需要安装 `jq`，然后在 shell 配置中加载脚本：

```bash
source /path/to/codex-glm-proxy/scripts/codex.sh
```

Windows 将 `scripts` 目录加入 `PATH` 后，可直接执行 `axg`、`axgs` 和 `axgf`。仓库内脚本默认使用当前项目作为代理目录；如果把脚本复制到其他目录，需要设置 `CODEX_GLM_PROXY_DIR`：

```powershell
$env:CODEX_GLM_PROXY_DIR = "D:\path\to\codex-glm-proxy"
```

## 测试

```bash
uv run python -m unittest discover -s tests -v
```

## 参考

协议转换设计参考了 MIT 许可的 [cc-switch](https://github.com/farion1231/cc-switch) Responses/Anthropic 转换模块，但本项目采用独立的 Python 标准库实现。
