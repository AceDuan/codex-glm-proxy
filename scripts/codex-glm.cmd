@echo off
setlocal DisableDelayedExpansion

set "CODEX_HOME=%USERPROFILE%\.codex-glm"
set "CODEX_GLM_KEY_FILE=%CODEX_HOME%\glm-api-key.json"
set "CODEX_GLM_ENV_FILE=%~dp0.env"
set "CODEX_GLM_PROXY_PORT=8766"
set "CODEX_GLM_PROXY_RUNTIME=%CODEX_HOME%\proxy-8766"
if not defined CODEX_GLM_PROXY_DIR if exist "%CODEX_GLM_ENV_FILE%" for /f "usebackq tokens=1,* delims== eol=#" %%A in ("%CODEX_GLM_ENV_FILE%") do if /i "%%A"=="CODEX_GLM_PROXY_DIR" set "CODEX_GLM_PROXY_DIR=%%B"
if not defined CODEX_GLM_PROXY_DIR (
    echo [ERROR] CODEX_GLM_PROXY_DIR is not configured. 1>&2
    echo [ERROR] Copy "%~dp0.env.example" to "%CODEX_GLM_ENV_FILE%" and set the project path. 1>&2
    exit /b 1
)

if not exist "%CODEX_GLM_KEY_FILE%" (
    echo [ERROR] Zhipu API key file not found: %CODEX_GLM_KEY_FILE% 1>&2
    exit /b 1
)

set "ZHIPU_API_KEY="
for /f "usebackq delims=" %%K in (`powershell.exe -NoProfile -NonInteractive -Command "$key=(ConvertFrom-Json -InputObject ([IO.File]::ReadAllText($env:CODEX_GLM_KEY_FILE))).ZHIPU_API_KEY; if ($key -isnot [string] -or [string]::IsNullOrWhiteSpace($key)) { exit 2 }; [Console]::Out.Write($key)" 2^>nul`) do set "ZHIPU_API_KEY=%%K"
if not defined ZHIPU_API_KEY (
    echo [ERROR] Invalid or missing ZHIPU_API_KEY in: %CODEX_GLM_KEY_FILE% 1>&2
    exit /b 1
)

if not exist "%CODEX_GLM_PROXY_DIR%\codex-glm-proxy.cmd" (
    echo [ERROR] Codex GLM proxy launcher not found: %CODEX_GLM_PROXY_DIR%\codex-glm-proxy.cmd 1>&2
    exit /b 1
)

call "%CODEX_GLM_PROXY_DIR%\codex-glm-proxy.cmd" start --port %CODEX_GLM_PROXY_PORT% --runtime-dir "%CODEX_GLM_PROXY_RUNTIME%"
if errorlevel 1 (
    echo [ERROR] Codex GLM proxy failed to start. Check: %CODEX_HOME%\proxy\proxy.log 1>&2
    exit /b 1
)

call codex -c "model_providers.custom.base_url='http://127.0.0.1:%CODEX_GLM_PROXY_PORT%/v1'" -c "mcp_servers.zhipu_web_search.command='npx'" -c "mcp_servers.zhipu_web_search.args=['--yes','mcp-remote@0.1.38','https://open.bigmodel.cn/api/mcp/web_search_prime/mcp','--header','Authorization: Bearer ${ZHIPU_API_KEY}','--transport','http-only','--silent']" -c "mcp_servers.zhipu_web_search.env_vars=['ZHIPU_API_KEY']" -c "mcp_servers.zhipu_web_search.enabled_tools=['web_search_prime']" -c "mcp_servers.zhipu_web_search.default_tools_approval_mode='approve'" %*
exit /b %errorlevel%
