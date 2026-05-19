@echo off
setlocal enabledelayedexpansion

:: Switch code page to UTF-8 to handle output correctly
chcp 65001 >nul

echo ==========================================
echo    Vision Driver Box Build Tool
echo ==========================================

:: 1. Input Version
set /p APP_VERSION="Enter version (e.g., 1.0.1, default 1.0.0): "
if "!APP_VERSION!"=="" set APP_VERSION=1.0.0

echo.
echo [1/4] Cleaning old build directories...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist setup_exe rmdir /s /q setup_exe

echo.
echo [2/4] Packaging Python code with PyInstaller...
python -m PyInstaller vsDriverBox.spec
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller failed!
    pause
    exit /b %errorlevel%
)

echo.
echo [3/4] Checking for Inno Setup Compiler (ISCC.exe)...
set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist !ISCC_PATH! (
    where iscc >nul 2>nul
    if %errorlevel% equ 0 (
        set ISCC_PATH=iscc
    ) else (
        echo [ERROR] ISCC.exe not found. Please install Inno Setup 6.
        pause
        exit /b 1
    )
)

echo.
echo [4/4] Compiling Installer (Version: !APP_VERSION!)...
!ISCC_PATH! /dAppVersion=!APP_VERSION! vsDriverBox_Setup.iss
if %errorlevel% neq 0 (
    echo [ERROR] Inno Setup compilation failed!
    pause
    exit /b %errorlevel%
)

:: 5. Post-build cleanup
echo.
echo [5/5] Post-build cleanup...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo.
echo ==========================================
echo    Build successful!
echo    Installer is in: setup_exe\
echo    Version: !APP_VERSION!
echo ==========================================
pause
