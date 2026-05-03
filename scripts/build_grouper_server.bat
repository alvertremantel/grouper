@echo off
REM build_grouper_server.bat — Compile grouper-server to grouper-server.exe via Nuitka
REM
REM Run from the project root with the venv active:
REM   .venv\Scripts\activate
REM   scripts\build_grouper_server.bat

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

python -c "import flask" 2>nul
if errorlevel 1 (
    echo ERROR: Flask is not installed.  pip install flask
    exit /b 1
)

set OPTIONAL_SERVER_FLAGS=

python -c "import zeroconf" 2>nul
if errorlevel 1 (
    echo WARNING: zeroconf is not installed. Server builds will exclude LAN discovery support.
) else (
    set OPTIONAL_SERVER_FLAGS=%OPTIONAL_SERVER_FLAGS% --include-package=zeroconf
)

echo ============================================================
echo  Grouper — Server Build
echo ============================================================
echo.
if defined GROUPER_NUITKA_LTO echo Nuitka LTO mode: %GROUPER_NUITKA_LTO%

echo Building grouper-server.exe (standalone)...
python -m nuitka ^
    --standalone ^
    --assume-yes-for-downloads ^
    --include-data-dir=server/web/templates=server/web/templates ^
    --include-package=grouper_core ^
    --include-package=grouper_core.database.migrations ^
    --include-package=grouper_sync ^
    --include-package=server.web ^
    %NUITKA_LTO_FLAG% ^
    %OPTIONAL_SERVER_FLAGS% ^
    --output-filename=grouper-server.exe ^
    --output-dir=dist ^
    --jobs=2 ^
    server\__main__.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

if exist "dist\grouper-server.dist" rmdir /s /q "dist\grouper-server.dist"
if exist "dist\grouper-server.build" rmdir /s /q "dist\grouper-server.build"
move /y "dist\__main__.dist" "dist\grouper-server.dist" >nul
if errorlevel 1 (
    echo ERROR: Failed to rename dist\__main__.dist to dist\grouper-server.dist
    exit /b 1
)
move /y "dist\__main__.build" "dist\grouper-server.build" >nul
if errorlevel 1 (
    echo ERROR: Failed to rename dist\__main__.build to dist\grouper-server.build
    exit /b 1
)

echo.
echo ============================================================
echo  Built: dist\grouper-server.dist\grouper-server.exe
echo ============================================================
