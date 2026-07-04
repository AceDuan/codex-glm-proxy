@echo off
call "%~dp0codex-glm.cmd" --sandbox danger-full-access --ask-for-approval never %*
exit /b %errorlevel%
