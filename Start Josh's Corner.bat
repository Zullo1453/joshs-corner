@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%CD%\.venv" (echo ERROR: .venv is missing.& pause & exit /b 1)
if not exist "%PYTHON%" (echo ERROR: project Python is missing.& pause & exit /b 1)
"%PYTHON%" -c "import flask, flask_wtf, flask_migrate, flask_sqlalchemy" >nul 2>&1 || (echo ERROR: required dependencies are missing. Run pip install -r requirements.txt.& pause & exit /b 1)
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000 -TimeoutSec 2; exit 0 } catch { exit 1 }"
if not errorlevel 1 (echo Josh's Corner is already running. Opening it now.& start "" http://127.0.0.1:5000& exit /b 0)
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 (echo ERROR: Port 5000 is in use by another application.& pause & exit /b 1)
start "Josh's Corner browser" /min powershell -NoProfile -Command "Start-Sleep -Seconds 2; try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000 -TimeoutSec 5 | Out-Null; Start-Process 'http://127.0.0.1:5000' } catch { }"
echo Starting Josh's Corner at http://127.0.0.1:5000
echo Press Ctrl+C to stop the server.
"%PYTHON%" run.py
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" echo ERROR: Server stopped unexpectedly. Review the messages above.
echo Server stopped. Press any key to close.
pause >nul
exit /b %EXITCODE%
