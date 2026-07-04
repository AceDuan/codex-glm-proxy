@echo off
codex --sandbox danger-full-access --ask-for-approval never %*
exit /b %errorlevel%
