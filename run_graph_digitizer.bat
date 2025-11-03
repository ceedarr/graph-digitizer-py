@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0" >nul
set "VENV=%~dp0.venv"

if not exist "%VENV%" (
    echo 仮想環境が見つかりません。作成中...
    call "%~dp0create_env.bat"
)

call "%VENV%\Scripts\activate.bat"
python graph_digitizer.py %*
set "RET=%ERRORLEVEL%"

if exist "%VENV%\Scripts\deactivate.bat" call "%VENV%\Scripts\deactivate.bat" >nul 2>&1

echo(
<nul set /p "=全ての処理が完了しました。Enterでウィンドウを閉じます。"
set /p dummy=

popd >nul
endlocal & exit /b %RET%
