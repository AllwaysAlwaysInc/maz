@echo off
cd /d "%~dp0"
start "" cmd /c "python server.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8910/mandaloz.html"
