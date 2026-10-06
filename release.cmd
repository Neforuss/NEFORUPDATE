@echo off
rem Builds a full NEFORUPDATE release into dist\:
rem   NEFORUPDATE-Setup-<ver>.exe     installer (Start menu, Settings > Apps, uninstaller)
rem   NEFORUPDATE-<ver>-portable.exe  single file, no install
rem   SHA256SUMS.txt                  checksums to publish next to the downloads
rem Needs: PyInstaller (python -m pip install --user pyinstaller) and Inno Setup 6 (iscc on PATH)
setlocal
cd /d "%~dp0"
for /f %%v in ('python -c "import neforupdate; print(neforupdate.__version__)"') do set VER=%%v
if "%VER%"=="" (echo Couldn't read the version from neforupdate\__init__.py & exit /b 1)
echo Building NEFORUPDATE %VER%

python -m PyInstaller --noconfirm --clean NEFORUPDATE.spec || goto :fail
python -m PyInstaller --noconfirm --clean NEFORUPDATE-installer.spec || goto :fail
python tools\make_installer_images.py || goto :fail
iscc /Q /DAppVersion=%VER% installer\neforupdate.iss || goto :fail

move /y dist\NEFORUPDATE.exe "dist\NEFORUPDATE-%VER%-portable.exe" >nul
powershell -NoProfile -Command "Get-ChildItem dist -File -Filter *.exe | Get-FileHash -Algorithm SHA256 | ForEach-Object { '{0}  {1}' -f $_.Hash.ToLower(), (Split-Path $_.Path -Leaf) } | Set-Content -Encoding ascii dist\SHA256SUMS.txt"
rmdir /s /q build 2>nul
echo.
echo Release %VER% is in %~dp0dist
type dist\SHA256SUMS.txt
exit /b 0

:fail
echo.
echo Build failed - see the output above.
exit /b 1
