@echo off
setlocal
chcp 65001 >nul
title 构建背单词助手 exe
cd /d "%~dp0"

echo [1/5] 检查构建环境…
where node >nul 2>nul
if errorlevel 1 goto :no_node
where npm >nul 2>nul
if errorlevel 1 goto :no_npm

if exist "backend\.venv\Scripts\python.exe" goto :install_deps
where python >nul 2>nul
if errorlevel 1 goto :no_python
echo 未找到 backend\.venv，正在创建虚拟环境…
python -m venv backend\.venv
if errorlevel 1 goto :fail

:install_deps
echo [2/5] 安装后端构建依赖…
backend\.venv\Scripts\python.exe -m pip install --quiet -r backend\requirements-build.txt
if errorlevel 1 goto :fail

echo [3/5] 构建前端…
cd frontend
if exist node_modules goto :build_frontend
call npm ci
if errorlevel 1 goto :fail
:build_frontend
call npm run build
if errorlevel 1 goto :fail
cd ..

echo [4/5] 打包 exe…
cd backend
.venv\Scripts\pyinstaller.exe --onefile --clean --noconfirm --name 背单词助手 ^
  --icon "%~dp0assets\app.ico" ^
  --version-file "%~dp0assets\version_info.txt" ^
  --paths "%~dp0backend" ^
  --add-data "%~dp0frontend\dist;app_static" ^
  --hidden-import app.main ^
  --hidden-import app.routers.backup ^
  --hidden-import sqlalchemy.dialects.mysql.pymysql ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import fsrs ^
  ..\launcher.py
if errorlevel 1 goto :fail
cd ..

echo [5/5] 复制许可与说明并生成校验和…
copy /y LICENSE backend\dist\ >nul
copy /y README.md backend\dist\ >nul
copy /y THIRD_PARTY_NOTICES.md backend\dist\ >nul
copy /y docs\PRIVACY.md backend\dist\ >nul
copy /y CHANGELOG.md backend\dist\ >nul
certutil -hashfile "backend\dist\背单词助手.exe" SHA256

echo.
echo 构建完成：backend\dist\背单词助手.exe
echo 可将 exe 与同目录的许可/说明文件一起复制到任意目录使用。
echo First run: edit the .env file in your AppData folder and fill in MySQL credentials.
pause
exit /b 0

:no_node
echo 未找到 Node.js，请安装 Node.js 20+ 后重试。
goto :fail

:no_npm
echo 未找到 npm，请安装 Node.js 20+ 后重试。
goto :fail

:no_python
echo 未找到 Python，请安装 Python 3.11 后重试。
goto :fail

:fail
echo.
echo 构建失败，请检查上方错误信息。
pause
exit /b 1
