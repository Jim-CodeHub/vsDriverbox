@echo off
setlocal enabledelayedexpansion

:: Switch code page to UTF-8 to handle output correctly
chcp 65001 >nul

echo ==========================================
echo    Vision Driver Box Build Tool
echo ==========================================

:: 1. Auto-extract Version from main.py
echo [0/5] Extracting version from main.py...

:: Use a temporary python command to write the version to a temp file to avoid CMD parsing issues
:: Use a more robust regex that accounts for potential line ending or quote issues
python -c "import re; content = open('main.py', encoding='utf-8').read(); m = re.search(r'APP_VERSION\s*=\s*[\x22\x27]([^\x22\x27]+)[\x22\x27]', content); print(m.group(1)) if m else exit(1)" > _version.tmp

if %errorlevel% neq 0 (
    echo [ERROR] Failed to extract version using Python.
    echo Please ensure main.py contains: APP_VERSION = \"1.0.0\"
    if exist _version.tmp del _version.tmp
    pause
    exit /b 1
)

set /p APP_VERSION=<_version.tmp
del _version.tmp

if "!APP_VERSION!"=="" (
    echo [ERROR] Could not extract APP_VERSION from main.py
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
