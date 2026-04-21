@echo off
REM build_setup.bat — Compile grouper_install/setup.py to setup.exe via Nuitka
REM
REM Run from the project root with the venv active:
REM   .venv\Scripts\activate
REM   scripts\build_setup.bat

setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set ICON=%PROJECT_ROOT%\grouper\assets\icon.ico

cd /d "%PROJECT_ROOT%"

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

REM Check for pywin32 (required for shortcut creation at runtime)
python -c "import win32com" 2>nul
if errorlevel 1 (
    echo Installing pywin32...
    pip install pywin32
)

REM Check for icon file
set ICON_FLAG=
if exist "%ICON%" (
    set ICON_FLAG=--windows-icon-from-ico=%ICON%
) else (
    echo WARNING: Icon not found at %ICON% — building without custom icon.
)

echo ============================================================
echo  Grouper — Installer Build
echo ============================================================
echo.

echo Building setup.exe...
python -m nuitka ^
    --onefile ^
    --assume-yes-for-downloads ^
    --windows-console-mode=disable ^
    --enable-plugin=pyside6 ^
    --include-package=win32com ^
    --include-package=win32api ^
    %ICON_FLAG% ^
    --output-filename=setup.exe ^
    --output-dir=dist ^
    --jobs=2 ^
    grouper_install\setup.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

echo.
echo ============================================================
echo  Built: dist\setup.exe
echo ============================================================
