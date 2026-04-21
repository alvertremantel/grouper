@echo off
REM build_release_final.bat — Full release build with LTO-enabled app, CLI, and server binaries
REM
REM Run from the project root with the venv active:
REM   .venv\Scripts\activate
REM   scripts\build_release_final.bat

setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

cd /d "%PROJECT_ROOT%"

set GROUPER_NUITKA_LTO=yes

echo ============================================================
echo  Grouper — Final Release Build
echo ============================================================
echo.
echo This build enables Nuitka LTO for:
echo   - grouper.exe
echo   - grouper-cli.exe
echo   - grouper-server.exe
echo.
echo Installer build remains on its normal settings.
echo.

call scripts\build_release.bat
set BUILD_EXIT=%ERRORLEVEL%

if not "%BUILD_EXIT%"=="0" (
    echo.
    echo FINAL RELEASE BUILD ABORTED.
    exit /b %BUILD_EXIT%
)

echo.
echo ============================================================
echo  Final Release Build Complete
echo ============================================================
echo.
echo Release variants are available under release\
echo.
