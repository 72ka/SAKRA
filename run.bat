@echo off
rem SAKRA - spusteni ve Windows
cd /d "%~dp0"
where uv >nul 2>nul
if %errorlevel%==0 (
  uv run sakra %*
) else (
  python -m sakra %*
)
if errorlevel 1 pause
