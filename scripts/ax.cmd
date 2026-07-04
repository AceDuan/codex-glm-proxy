@echo off
codex --sandbox workspace-write --ask-for-approval on-request %*
exit /b %errorlevel%
