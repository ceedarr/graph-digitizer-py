@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "VENV=%SCRIPT_DIR%.venv"

python -m venv "%VENV%"
call "%VENV%\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install numpy pillow
if exist "%VENV%\Scripts\deactivate.bat" call "%VENV%\Scripts\deactivate.bat" >nul 2>&1
endlocal
