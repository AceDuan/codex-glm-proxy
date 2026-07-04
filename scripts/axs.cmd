@echo off
codex --sandbox workspace-write --ask-for-approval on-request --search %*
exit /b %errorlevel%
