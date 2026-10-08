@echo off
rem Kaynnistaa paikallisen palvelimen ja avaa sivun selaimeen. Sulje ikkuna (tai Ctrl+C) lopettaaksesi.
cd /d "%~dp0"
start "" http://localhost:8765
python -m http.server 8765 --directory site
