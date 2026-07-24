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

代理会过滤没有直接等价能力的 Responses 内置 `web_search` 和 `image_generation` 工具，不实现 `/v1/responses/compact`。GLM 快捷命令会另外注入智谱的联网搜索 MCP，不依赖被过滤的内置 `web_search`。

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
| `axg` | GLM | `workspace-write` / `on-request` | 智谱联网搜索 MCP |
| `axgs` | GLM | `workspace-write` / `on-request` | 智谱联网搜索 MCP（兼容别名） |
| `axgf` | GLM | `danger-full-access` / `never` | 智谱联网搜索 MCP |

所有 GLM 快捷命令都会在当前 Codex 进程中临时注册智谱的联网搜索 MCP。由于当前 Codex 对部分 Remote HTTP MCP 的初始化响应存在兼容性问题，命令会用 `mcp-remote@0.1.38` 作为本地 stdio 桥接器访问智谱服务。脚本不会写入 `~/.codex-glm/config.toml`，并且仅通过子进程环境变量把 `glm-api-key.json` 中的 `ZHIPU_API_KEY` 传给桥接器。仅 `web_search_prime` 会暴露给模型并自动批准，其他桥接工具不会获得权限。模型仅在判断任务需要联网时调用该工具；例如可直接要求“搜索最新的某项技术文档”。`axgs` 保留为与 `axg` 相同的兼容别名，不再依赖 Codex 原生 `--search`。

除 WSL 所需的 `jq` 外，GLM 快捷命令还需要可用的 `npx`，以便按需运行这一桥接器。

WSL 需要安装 `jq`，然后在 shell 配置中加载脚本：

```bash
source /path/to/codex-glm-proxy/scripts/codex.sh
```

Windows 将 `scripts` 目录加入 `PATH` 后，可直接执行 `axg`、`axgs` 和 `axgf`。首次使用时复制环境配置示例并填写项目的绝对路径：

```powershell
Copy-Item scripts\.env.example scripts\.env
# 编辑 scripts\.env 中的 CODEX_GLM_PROXY_DIR
```

`scripts/.env` 是本机配置且不会提交；也可以直接设置同名环境变量覆盖该文件中的值。

## 测试

```bash
uv run python -m unittest discover -s tests -v
```

## 参考

协议转换设计参考了 MIT 许可的 [cc-switch](https://github.com/farion1231/cc-switch) Responses/Anthropic 转换模块，但本项目采用独立的 Python 标准库实现。
