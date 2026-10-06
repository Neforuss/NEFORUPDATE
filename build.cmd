@echo off
rem Builds dist\NEFORUPDATE.exe from NEFORUPDATE.spec (icon, 720p splash, version info, assets).
rem Needs: python -m pip install --user pyinstaller
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean NEFORUPDATE.spec
echo.
if exist dist\NEFORUPDATE.exe (echo Built: %~dp0dist\NEFORUPDATE.exe) else (echo Build failed - see output above)
