@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where python.exe >nul 2>&1
if errorlevel 1 goto python_missing

python.exe -c "import tkinter, selenium" >nul 2>&1
if errorlevel 1 goto dependency_missing
if /i "%~1"=="--check" exit /b 0

where pythonw.exe >nul 2>&1
if errorlevel 1 goto console_start

start "" pythonw.exe "%~dp0src\wenjuanxing_gui.py"
exit /b 0

:console_start
python.exe "%~dp0src\wenjuanxing_gui.py"
if errorlevel 1 goto start_failed
exit /b 0

:python_missing
echo 未找到 Python，请先安装 Python 并将其加入 PATH。
goto show_error

:dependency_missing
echo 当前 Python 缺少 tkinter 或 selenium 依赖。
echo 请在本目录执行：python -m pip install -r requirements.txt
goto show_error

:start_failed
echo 图形界面启动失败。

:show_error
echo.
pause
exit /b 1
