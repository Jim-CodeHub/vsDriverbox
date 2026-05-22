@echo off
setlocal enabledelayedexpansion

:: Switch code page to UTF-8 to handle output correctly
chcp 65001 >nul

echo ==========================================
echo    Vision Driver Box Build Tool
echo ==========================================

:: 1. Auto-extract Version from main.py
echo [0/5] Extracting version from main.py...

for /f "tokens=2 delims==" %%a in ('findstr /C:"APP_VERSION =" main.py') do (
    set "RAW_VERSION=%%a"
    :: Remove spaces
    set "RAW_VERSION=!RAW_VERSION: =!"
    :: Remove double quotes
    set "RAW_VERSION=!RAW_VERSION:"=!"
    :: Remove single quotes
    set "RAW_VERSION=!RAW_VERSION:'=!"
    set "APP_VERSION=!RAW_VERSION!"
)

if "!APP_VERSION!"=="" (
    echo [ERROR] APP_VERSION variable is empty.
    pause
    exit /b 1
)

echo Detected Version: !APP_VERSION!

echo.
echo [1/5] Cleaning old build directories...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist setup_exe rmdir /s /q setup_exe

echo.
echo [2/5] Packaging Python code with PyInstaller...
python -m PyInstaller vsDriverBox.spec
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller failed!
    pause
    exit /b %errorlevel%
)

echo.
echo [3/5] Checking for Inno Setup Compiler (ISCC.exe)...
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
echo [4/5] Compiling Installer (Version: !APP_VERSION!)...
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
