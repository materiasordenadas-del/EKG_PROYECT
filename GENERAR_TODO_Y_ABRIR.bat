@echo off
setlocal
cd /d "%~dp0"

if exist "output\ECG_BANCO_INICIAL_REAL\ABRIR_VISOR.bat" (
  echo El banco local ya existe. Se abrira sin descargar archivos.
  start "" "output\ECG_BANCO_INICIAL_REAL\ABRIR_VISOR.bat"
  exit /b 0
)

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python no esta instalado o no esta en PATH.
  echo Instala Python 3.11 o superior y marca Add Python to PATH.
  pause
  exit /b 1
)

echo Instalando dependencias necesarias...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo ERROR: No se pudieron instalar las dependencias.
  pause
  exit /b 1
)

echo.
echo Descargando y preparando ocho ECG reales de PTB-XL...
python tools\build_ecg_bank.py
if errorlevel 1 (
  echo.
  echo ERROR: No se pudo completar el banco.
  pause
  exit /b 1
)

echo.
echo LISTO. Se abrira el visor.
start "" "output\ECG_BANCO_INICIAL_REAL\ABRIR_VISOR.bat"
exit /b 0
