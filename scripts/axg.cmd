@echo off
call "%~dp0codex-glm.cmd" --sandbox workspace-write --ask-for-approval on-request %*
exit /b %errorlevel%
