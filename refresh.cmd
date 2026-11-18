@echo off
rem Double-click to refresh the local warehouse and dashboard (Windows).
cd /d "%~dp0"
".venv\Scripts\python.exe" refresh.py %*
echo.
pause
