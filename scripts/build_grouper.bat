@echo off
REM build_grouper.bat — Compile desktop Grouper to grouper.exe via Nuitka
REM
REM Run from the project root with the venv active:
REM   .venv\Scripts\activate
REM   scripts\build_grouper.bat

setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set ICON=%PROJECT_ROOT%\grouper\assets\icon.ico

cd /d "%PROJECT_ROOT%"

set NUITKA_LTO_FLAG=
if defined GROUPER_NUITKA_LTO (
    if /i not "%GROUPER_NUITKA_LTO%"=="yes" if /i not "%GROUPER_NUITKA_LTO%"=="no" (
        echo ERROR: GROUPER_NUITKA_LTO must be yes or no. Got "%GROUPER_NUITKA_LTO%".
        exit /b 1
    )
    set NUITKA_LTO_FLAG=--lto=%GROUPER_NUITKA_LTO%
)

REM --- Preflight checks ---

python -c "import nuitka" 2>nul
if errorlevel 1 (
    echo ERROR: Nuitka is not installed.  pip install nuitka
    exit /b 1
)

python -c "import PySide6" 2>nul
if errorlevel 1 (
    echo ERROR: PySide6 is not installed.  pip install PySide6
    exit /b 1
)

set OPTIONAL_SYNC_FLAGS=
python -c "import zeroconf" 2>nul
if errorlevel 1 (
    echo WARNING: zeroconf is not installed. Desktop sync builds will exclude LAN discovery support.
) else (
    set OPTIONAL_SYNC_FLAGS=--include-package=zeroconf
)

REM Check for icon file
set ICON_FLAG=
if exist "%ICON%" (
    set ICON_FLAG=--windows-icon-from-ico=%ICON%
) else (
    echo WARNING: Icon not found at %ICON% — building without custom icon.
)

echo ============================================================
echo  Grouper — Main Application Build
echo ============================================================
echo.
if defined GROUPER_NUITKA_LTO echo Nuitka LTO mode: %GROUPER_NUITKA_LTO%

echo Building grouper.exe (standalone)...
python -m nuitka ^
    --standalone ^
    --assume-yes-for-downloads ^
    --windows-console-mode=disable ^
    --enable-plugin=pyside6 ^
    --include-data-files=grouper/styles/_base.qss=grouper/styles/_base.qss ^
    --include-data-files=grouper/assets/icon.ico=grouper/assets/icon.ico ^
    --include-data-files=pyproject.toml=pyproject.toml ^
    --include-package=grouper_core ^
    --include-package=grouper_core.database.migrations ^
    --include-package=grouper_server.sync ^
    %ICON_FLAG% ^
    %NUITKA_LTO_FLAG% ^
    %OPTIONAL_SYNC_FLAGS% ^
    --output-filename=grouper.exe ^
    --output-dir=dist ^
    --jobs=2 ^
    grouper\main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

if exist "dist\grouper.dist" rmdir /s /q "dist\grouper.dist"
if exist "dist\grouper.build" rmdir /s /q "dist\grouper.build"
move /y "dist\main.dist" "dist\grouper.dist" >nul
if errorlevel 1 (
    echo ERROR: Failed to rename dist\main.dist to dist\grouper.dist
    exit /b 1
)
move /y "dist\main.build" "dist\grouper.build" >nul
if errorlevel 1 (
    echo ERROR: Failed to rename dist\main.build to dist\grouper.build
    exit /b 1
)

echo.
echo ============================================================
echo  Built: dist\grouper.dist\grouper.exe
echo ============================================================
