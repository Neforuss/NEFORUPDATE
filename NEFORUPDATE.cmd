@echo off
rem Opens NEFORUPDATE from source without a console window.
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw main.py) || (start "" python main.py)
