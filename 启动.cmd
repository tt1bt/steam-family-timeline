@echo off
chcp 65001 >nul
title Steam 家庭组时间线
cd /d "%~dp0"

echo.
echo   正在启动 Steam 家庭组时间线...
echo.

REM 优先使用 WorkBuddy 内置的 Python，其次用系统 python
set "PY="
if exist "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" (
  set "PY=%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
)
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  where py >nul 2>nul && set "PY=py"
)

if not defined PY (
  echo   [错误] 没找到 Python。
  echo   请先安装 Python 3.9+ : https://www.python.org/downloads/
  echo   安装时记得勾选 "Add Python to PATH"。
  echo.
  pause
  exit /b 1
)

echo   使用 Python: %PY%
echo.
"%PY%" "src\server.py" %*

echo.
echo   服务已退出。
pause
