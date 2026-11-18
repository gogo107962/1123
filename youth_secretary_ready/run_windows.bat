@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -X utf8 -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -X utf8 start.py
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Startup failed. Check the error above.
pause
exit /b 1
