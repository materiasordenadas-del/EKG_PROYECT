@echo off
setlocal
cd /d "%~dp0"

echo ================================================
echo  Banco de pruebas AFIB - PTB-XL 500 Hz
echo ================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python no esta instalado o no esta en PATH.
  echo Instala Python 3.11 o superior y marca Add Python to PATH.
  pause
  exit /b 1
)

echo Instalando o comprobando dependencias...
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo ERROR: No se pudieron instalar las dependencias.
  pause
  exit /b 1
)

echo.
echo Descargando y preparando 20 ECG de fibrilacion auricular...
python tools\build_test_candidates.py
if errorlevel 1 (
  echo.
  echo ERROR: No se pudo completar el banco de pruebas.
  echo Revisa el mensaje anterior y vuelve a ejecutar este archivo.
  pause
  exit /b 1
)

echo.
echo LISTO. Abriendo el visor de revision...
start "" "testing\ABRIR_REVISION.html"
exit /b 0
