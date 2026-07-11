@echo off
setlocal
cd /d "%~dp0"

if not exist "viewer\index.html" (
  echo ERROR: No existe viewer\index.html
  pause
  exit /b 1
)
if not exist "catalog\rhythms_catalog.json" (
  echo ERROR: No existe catalog\rhythms_catalog.json
  pause
  exit /b 1
)

set "PORT=8765"
where py >nul 2>nul
if %errorlevel%==0 (
  start "Servidor ECG" /min cmd /c "cd /d ""%~dp0"" && py -m http.server %PORT% --bind 127.0.0.1"
  powershell -NoProfile -Command "Start-Sleep -Milliseconds 1200" >nul 2>nul
  start "" "http://127.0.0.1:%PORT%/viewer/index.html"
  exit /b 0
)
where python >nul 2>nul
if %errorlevel%==0 (
  start "Servidor ECG" /min cmd /c "cd /d ""%~dp0"" && python -m http.server %PORT% --bind 127.0.0.1"
  powershell -NoProfile -Command "Start-Sleep -Milliseconds 1200" >nul 2>nul
  start "" "http://127.0.0.1:%PORT%/viewer/index.html"
  exit /b 0
)

echo ERROR: No se encontro Python 3.
pause
exit /b 1
