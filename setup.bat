@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  sw-draw-skill 环境安装/检测脚本
echo ============================================

set "PY="
where python >nul 2>nul
if %errorlevel%==0 set "PY=python"
if not defined PY (
  where py >nul 2>nul
  if %errorlevel%==0 set "PY=py"
)

if not defined PY (
  echo.
  echo [提示] 未检测到 Python。
  choice /c YN /m "是否尝试自动安装 Python（winget 安装 Python 3.12）?"
  if errorlevel 2 goto :skip_python
  echo 正在尝试通过 winget 安装 Python...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  where python >nul 2>nul
  if %errorlevel%==0 set "PY=python"
  if not defined PY (
    where py >nul 2>nul
    if %errorlevel%==0 set "PY=py"
  )
  if not defined PY (
    echo.
    echo [失败] Python 安装未完成，请手动安装后重新运行本脚本。
    echo 下载地址: https://www.python.org/downloads/
    goto :skip_python
  )
)

:skip_python
if not defined PY (
  echo.
  echo [跳过] 未安装 Python，插件核心功能需要 Python 才能运行。
  echo 您可以手动安装 Python 后，再运行 setup.bat。
  echo.
  echo 但以下环境检测仍会继续：
)

echo.
echo [1/4] 检测 SolidWorks COM 注册...
if not defined PY (
  echo  - 因无 Python，无法自动检测 SW COM，请确认 SolidWorks 2018 已安装。
) else (
  %PY% -c "import win32com.client; win32com.client.Dispatch('SldWorks.Application'); print('  - SolidWorks COM OK')" 2>nul
  if errorlevel 1 echo  - SolidWorks COM 未检测到（请确认已安装 SolidWorks 2018，或首次运行稍后重试）。
)

if not defined PY goto :finish

echo.
echo [2/4] 安装 Python 依赖...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo [失败] 依赖安装失败，请检查网络或 Python 版本。
  goto :finish
)

echo.
echo [3/4] 生成 SolidWorks 2018 COM 缓存...
%PY% -c "from win32com.client import gencache; gencache.EnsureModule('{83A33D31-27C5-11CE-BFD4-00400513BB57}', 0, 26, 0)"
if errorlevel 1 echo  - 缓存生成失败，请确认 SW2018 COM 类型库正常。

echo.
echo [4/4] 运行环境自检...
%PY% verify_env.py

:finish
echo.
echo ============================================
echo  安装/检测结束。
echo  详细说明见 docs/移植与打包说明.md
echo  MCP 桌面客户端配置见 docs/桌面客户端接入说明.md
echo ============================================
endlocal
