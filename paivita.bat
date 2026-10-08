@echo off
rem Hakee uuden datan ja laskee sivun JSON-tiedostot. Loki: paivitys.log
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> paivitys.log
python scripts\fetch_all.py >> paivitys.log 2>&1
python scripts\build.py >> paivitys.log 2>&1
if errorlevel 1 (
  echo Laskenta epaonnistui, katso paivitys.log
  exit /b 1
)
echo Valmis. Avaa sivu: nayta.bat
