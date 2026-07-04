@echo off
setlocal DisableDelayedExpansion

set "CODEX_HOME=%USERPROFILE%\.codex-glm"
set "CODEX_GLM_KEY_FILE=%CODEX_HOME%\glm-api-key.json"
if not defined CODEX_GLM_PROXY_DIR for %%I in ("%~dp0..") do set "CODEX_GLM_PROXY_DIR=%%~fI"

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

call "%CODEX_GLM_PROXY_DIR%\codex-glm-proxy.cmd" start
if errorlevel 1 (
    echo [ERROR] Codex GLM proxy failed to start. Check: %CODEX_HOME%\proxy\proxy.log 1>&2
    exit /b 1
)

call codex -c model_providers.custom.base_url=\"http://127.0.0.1:8765/v1\" %*
exit /b %errorlevel%
