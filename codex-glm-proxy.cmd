@echo off
setlocal
if defined UV_EXE if exist "%UV_EXE%" set "UV=%UV_EXE%"
if not defined UV for /f "delims=" %%I in ('where uv 2^>nul') do if not defined UV set "UV=%%I"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV if exist "%USERPROFILE%\.local\uv-folder\uv.exe" set "UV=%USERPROFILE%\.local\uv-folder\uv.exe"
if not defined UV (
    echo [ERROR] uv was not found. Add it to PATH or set UV_EXE. 1>&2
    exit /b 1
)
pushd "%~dp0"
"%UV%" run codex-glm-proxy %*
set "RC=%errorlevel%"
popd
exit /b %RC%
