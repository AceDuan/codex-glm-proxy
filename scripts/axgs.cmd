@echo off
call "%~dp0codex-glm.cmd" --sandbox workspace-write --ask-for-approval on-request --search %*
exit /b %errorlevel%
