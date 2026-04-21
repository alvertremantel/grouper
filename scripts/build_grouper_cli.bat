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

echo Building grouper-cli.exe (standalone)...
python -m nuitka ^
    --standalone ^
    --assume-yes-for-downloads ^
    --include-package=grouper_core ^
    --include-package=grouper_core.database.migrations ^
    --output-filename=grouper-cli.exe ^
    --output-dir=dist ^
    --jobs=2 ^
    grouper_cli\main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

if exist "dist\grouper-cli.dist" rmdir /s /q "dist\grouper-cli.dist"
if exist "dist\grouper-cli.build" rmdir /s /q "dist\grouper-cli.build"
move /y "dist\main.dist" "dist\grouper-cli.dist" >nul
move /y "dist\main.build" "dist\grouper-cli.build" >nul

echo.
echo ============================================================
echo  Built: dist\grouper-cli.dist\grouper-cli.exe
echo ============================================================
