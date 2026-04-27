@echo off
REM build_grouper_cli.bat — Compile grouper-cli to grouper-cli.exe via Nuitka
REM
REM Run from the project root with the venv active:
REM   .venv\Scripts\activate
REM   scripts\build_grouper_cli.bat

setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

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

echo ============================================================
echo  Grouper — CLI Build
echo ============================================================
echo.
if defined GROUPER_NUITKA_LTO echo Nuitka LTO mode: %GROUPER_NUITKA_LTO%

echo Building grouper-cli.exe (standalone)...
python -m nuitka ^
    --standalone ^
    --assume-yes-for-downloads ^
    --include-package=grouper_core ^
    --include-package=grouper_core.database.migrations ^
    %NUITKA_LTO_FLAG% ^
    --output-filename=grouper-cli.exe ^
    --output-dir=dist ^
    --jobs=2 ^
    cli\main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

if exist "dist\grouper-cli.dist" rmdir /s /q "dist\grouper-cli.dist"
if exist "dist\grouper-cli.build" rmdir /s /q "dist\grouper-cli.build"
move /y "dist\main.dist" "dist\grouper-cli.dist" >nul
if errorlevel 1 (
    echo ERROR: Failed to rename dist\main.dist to dist\grouper-cli.dist
    exit /b 1
)
move /y "dist\main.build" "dist\grouper-cli.build" >nul
if errorlevel 1 (
    echo ERROR: Failed to rename dist\main.build to dist\grouper-cli.build
    exit /b 1
)

echo.
echo ============================================================
echo  Built: dist\grouper-cli.dist\grouper-cli.exe
echo ============================================================
