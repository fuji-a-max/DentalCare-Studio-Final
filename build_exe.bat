@echo off
setlocal
cd /d "%~dp0"
echo Installing build dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
python -m PyInstaller --noconfirm --clean --onefile --windowed --name "DentalCare Studio" --icon "static\logo.ico" --add-data "static;static" --collect-all webview --hidden-import clr desktop_app.py
if errorlevel 1 goto :fail
echo.
echo SUCCESS: dist\DentalCare Studio.exe
pause
exit /b 0
:fail
echo Build failed. Check Python, dependencies and WebView2.
pause
exit /b 1
endlocal
