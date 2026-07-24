ax() {
  codex \
    --sandbox workspace-write \
    --ask-for-approval on-request \
    "$@"
}

axs() {
  codex \
    --sandbox workspace-write \
    --ask-for-approval on-request \
    --search \
    "$@"
}

axf() {
  codex \
    --sandbox danger-full-access \
    --ask-for-approval never \
    "$@"
}

codex-glm() {
  local codex_home="$HOME/.codex-glm"
  local key_file="$codex_home/glm-api-key.json"
  local proxy_dir
  local api_key

  proxy_dir="${CODEX_GLM_PROXY_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"

  if [[ ! -r "$key_file" ]]; then
    echo "智谱 API Key 文件不存在或不可读：$key_file" >&2
    return 1
  fi

  api_key="$(jq -er '.ZHIPU_API_KEY | select(type == "string" and length > 0)' "$key_file")" || {
    echo "智谱 API Key 文件格式错误或缺少 ZHIPU_API_KEY：$key_file" >&2
    return 1
  }

  uv run --directory "$proxy_dir" codex-glm-proxy start || {
    echo "Codex GLM 代理启动失败，请检查：$codex_home/proxy/proxy.log" >&2
    return 1
  }

  CODEX_HOME="$codex_home" \
  ZHIPU_API_KEY="$api_key" \
    codex \
      -c 'model_providers.custom.base_url="http://127.0.0.1:8765/v1"' \
      -c 'mcp_servers.zhipu_web_search.command="npx"' \
      -c 'mcp_servers.zhipu_web_search.args=["--yes","mcp-remote@0.1.38","https://open.bigmodel.cn/api/mcp/web_search_prime/mcp","--header","Authorization: Bearer ${ZHIPU_API_KEY}","--transport","http-only","--silent"]' \
      -c 'mcp_servers.zhipu_web_search.env_vars=["ZHIPU_API_KEY"]' \
      -c 'mcp_servers.zhipu_web_search.enabled_tools=["web_search_prime"]' \
      -c 'mcp_servers.zhipu_web_search.default_tools_approval_mode="approve"' \
      "$@"
}

axg() {
  codex-glm \
    --sandbox workspace-write \
    --ask-for-approval on-request \
    "$@"
}

axgs() {
  axg "$@"
}

axgf() {
  codex-glm \
    --sandbox danger-full-access \
    --ask-for-approval never \
    "$@"
}
