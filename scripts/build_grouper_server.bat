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

if /i "%GROUPER_INCLUDE_TUI%"=="1" (
    python -c "import textual" 2>nul
    if errorlevel 1 (
        echo ERROR: GROUPER_INCLUDE_TUI=1 was set, but textual is not installed.  pip install textual
        exit /b 1
    )
    set OPTIONAL_SERVER_FLAGS=%OPTIONAL_SERVER_FLAGS% --include-package=grouper_server.tui --include-package=textual
) else (
    echo NOTE: Textual TUI is excluded by default. Set GROUPER_INCLUDE_TUI=1 to bundle it.
)

echo ============================================================
echo  Grouper — Server Build
echo ============================================================
echo.

echo Building grouper-server.exe (standalone)...
python -m nuitka ^
    --standalone ^
    --assume-yes-for-downloads ^
    --include-data-dir=grouper_server/web/templates=grouper_server/web/templates ^
    --include-package=grouper_core ^
    --include-package=grouper_core.database.migrations ^
    --include-package=grouper_server.sync ^
    --include-package=grouper_server.web ^
    %OPTIONAL_SERVER_FLAGS% --output-filename=grouper-server.exe ^
    --output-dir=dist ^
    --jobs=2 ^
    grouper_server\__main__.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

if exist "dist\grouper-server.dist" rmdir /s /q "dist\grouper-server.dist"
if exist "dist\grouper-server.build" rmdir /s /q "dist\grouper-server.build"
move /y "dist\__main__.dist" "dist\grouper-server.dist" >nul
move /y "dist\__main__.build" "dist\grouper-server.build" >nul

echo.
echo ============================================================
echo  Built: dist\grouper-server.dist\grouper-server.exe
echo ============================================================
