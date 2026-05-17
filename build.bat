@echo off
setlocal enabledelayedexpansion

:: ==========================================
:: vsDriverBox 一键打包分发脚本
:: ==========================================

echo.
echo ==========================================
echo    Vision Driver Box 自动化打包工具
echo ==========================================
echo.

:: 1. 输入版本号
set /p APP_VERSION="请输入版本号 (例如 1.0.1, 直接回车默认为 1.0.0): "
if "!APP_VERSION!"=="" set APP_VERSION=1.0.0

echo.
echo [1/4] 正在清理旧的构建目录...
if exist dist rd /s /q dist
if exist build rd /s /q build
if exist installer_output rd /s /q installer_output

echo.
echo [2/4] 正在使用 PyInstaller 打包 Python 代码...
:: 使用 python -m PyInstaller 确保使用当前环境的模块
python -m PyInstaller vsDriverBox.spec
if %errorlevel% neq 0 (
    echo.
    echo [错误] PyInstaller 打包失败！
    pause
    exit /b %errorlevel%
)

echo.
echo [3/4] 正在检测 Inno Setup 编译器 (ISCC.exe)...
:: 尝试从默认路径或 PATH 中查找 ISCC
set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist !ISCC_PATH! (
    :: 如果默认路径不存在，尝试从 PATH 查找
    where iscc >nul 2>nul
    if %errorlevel% equ 0 (
        set ISCC_PATH=iscc
    ) else (
        echo.
        echo [错误] 未能找到 Inno Setup 编译器 (ISCC.exe)。
        echo 请确保已安装 Inno Setup 6，或将其添加到系统 PATH 中。
        pause
        exit /b 1
    )
)

echo.
echo [4/4] 正在编译安装包 (版本: !APP_VERSION!)...
:: 通过 /d 定义参数传递版本号给 ISS 脚本
!ISCC_PATH! /dAppVersion=!APP_VERSION! vsDriverBox_Setup.iss
if %errorlevel% neq 0 (
    echo.
    echo [错误] Inno Setup 编译失败！
    pause
    exit /b %errorlevel%
)

echo.
echo ==========================================
echo    打包成功完成！
echo    安装包位于: installer_output\
echo    版本号: !APP_VERSION!
echo ==========================================
echo.
pause
