@echo off
REM build_release.bat — Full release build: four variants with different component combinations
REM
REM Run from the project root with the venv active:
REM   .venv\Scripts\activate
REM   scripts\build_release.bat
REM
REM Produces four release variants under release/:
REM   core/            — app + setup.exe + docs
REM   core_cli/        — app + cli + setup.exe + docs
REM   core_server/     — app + server + setup.exe + docs
REM   core_cli_server/ — app + cli + server + setup.exe + docs

setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set RELEASE_DIR=%PROJECT_ROOT%\release
set DIST_DIR=%PROJECT_ROOT%\dist

cd /d "%PROJECT_ROOT%"

echo ============================================================
echo  Grouper — Full Release Build (Four Variants)
echo ============================================================
echo.

REM --- Clean release directory ---
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

REM --- Step 1: Build grouper.exe ---
echo [1/5] Building grouper.exe...
echo.
call scripts\build_grouper.bat
if errorlevel 1 (
    echo.
    echo RELEASE BUILD ABORTED — grouper.exe build failed.
    exit /b 1
)
echo.

REM --- Step 2: Build grouper-cli.exe ---
echo [2/5] Building grouper-cli.exe...
echo.
call scripts\build_grouper_cli.bat
if errorlevel 1 (
    echo.
    echo RELEASE BUILD ABORTED — grouper-cli.exe build failed.
    exit /b 1
)
echo.

REM --- Step 3: Build grouper-server.exe ---
echo [3/5] Building grouper-server.exe...
echo.
call scripts\build_grouper_server.bat
if errorlevel 1 (
    echo.
    echo RELEASE BUILD ABORTED — grouper-server.exe build failed.
    exit /b 1
)
echo.

REM --- Step 4: Build setup.exe ---
echo [4/5] Building setup.exe...
echo.
call scripts\build_setup.bat
if errorlevel 1 (
    echo.
    echo RELEASE BUILD ABORTED — setup.exe build failed.
    exit /b 1
)
echo.

REM --- Verify required build outputs exist ---
if not exist "%DIST_DIR%\grouper.dist" (
    echo ERROR: Required build output not found: dist\grouper.dist
    echo RELEASE BUILD ABORTED — main application is missing.
    exit /b 1
)

if not exist "%DIST_DIR%\setup.exe" (
    echo ERROR: Required build output not found: dist\setup.exe
    echo RELEASE BUILD ABORTED — installer is missing.
    exit /b 1
)

REM --- Check for optional build outputs ---
set CLI_AVAILABLE=0
set SERVER_AVAILABLE=0

if exist "%DIST_DIR%\grouper-cli.dist" (
    set CLI_AVAILABLE=1
) else (
    echo WARNING: dist\grouper-cli.dist not found — CLI variants will be skipped.
)

if exist "%DIST_DIR%\grouper-server.dist" (
    set SERVER_AVAILABLE=1
) else (
    echo WARNING: dist\grouper-server.dist not found — server variants will be skipped.
)

echo.
echo [5/5] Assembling release variants...
echo.

REM --- Assemble variants ---
call :assemble_variant core 0 0
if errorlevel 1 exit /b 1
call :assemble_variant core_cli 1 0
if errorlevel 1 exit /b 1
call :assemble_variant core_server 0 1
if errorlevel 1 exit /b 1
call :assemble_variant core_cli_server 1 1
if errorlevel 1 exit /b 1

echo.
echo ============================================================
echo  Release Variants Assembled
echo ============================================================
echo.
echo  Variants produced:
echo.

if exist "%RELEASE_DIR%\core" (
    echo    release\core\            — Application + Installer + Docs
)
if exist "%RELEASE_DIR%\core_cli" (
    echo    release\core_cli\        — Application + CLI + Installer + Docs
)
if exist "%RELEASE_DIR%\core_server" (
    echo    release\core_server\     — Application + Server + Installer + Docs
)
if exist "%RELEASE_DIR%\core_cli_server" (
    echo    release\core_cli_server\ — Application + CLI + Server + Installer + Docs
)

echo.
echo  Each variant contains:
echo    app\         — Main application (grouper.exe standalone)
echo    cli\         — CLI tool (grouper-cli.exe) [when included]
echo    server\      — Sync/web server (grouper-server.exe) [when included]
echo    dist.toml    — Release variant metadata
echo    setup.exe    — Installer
echo    README.md    — User documentation
echo    LICENSE      — Apache 2.0 license
echo    version.txt  — Release version
echo.
echo  Next steps:
echo    1. Smoke test each variant: cd release\core\app ^& grouper.exe
echo    2. Test installers: release\core\setup.exe
echo    3. Zip each variant folder for distribution
echo ============================================================

goto :eof

REM ============================================================
REM Subroutine: assemble_variant
REM Args: %1 = variant folder name, %2 = include CLI (1/0), %3 = include server (1/0)
REM ============================================================
:assemble_variant
set VARIANT_NAME=%1
set INCLUDE_CLI=%2
set INCLUDE_SERVER=%3

REM Skip if CLI is required but not available
if %INCLUDE_CLI%==1 (
    if %CLI_AVAILABLE%==0 (
        echo Skipping %VARIANT_NAME% — CLI build not available.
        goto :eof
    )
)

REM Skip if server is required but not available
if %INCLUDE_SERVER%==1 (
    if %SERVER_AVAILABLE%==0 (
        echo Skipping %VARIANT_NAME% — server build not available.
        goto :eof
    )
)

echo Assembling %VARIANT_NAME%...

set VARIANT_DIR=%RELEASE_DIR%\%VARIANT_NAME%
mkdir "%VARIANT_DIR%"

REM Copy main application (required for all variants)
xcopy /e /i /q "%DIST_DIR%\grouper.dist" "%VARIANT_DIR%\app" >nul
if errorlevel 1 (
    echo ERROR: Failed to copy app to %VARIANT_NAME%
    exit /b 1
)

REM Copy CLI if requested
if %INCLUDE_CLI%==1 (
    xcopy /e /i /q "%DIST_DIR%\grouper-cli.dist" "%VARIANT_DIR%\cli" >nul
    if errorlevel 1 (
        echo ERROR: Failed to copy cli to %VARIANT_NAME%
        exit /b 1
    )
)

REM Copy server if requested
if %INCLUDE_SERVER%==1 (
    xcopy /e /i /q "%DIST_DIR%\grouper-server.dist" "%VARIANT_DIR%\server" >nul
    if errorlevel 1 (
        echo ERROR: Failed to copy server to %VARIANT_NAME%
        exit /b 1
    )
)

REM Copy setup.exe (required for all variants)
copy "%DIST_DIR%\setup.exe" "%VARIANT_DIR%\setup.exe" >nul
if errorlevel 1 (
    echo ERROR: Failed to copy setup.exe to %VARIANT_NAME%
    exit /b 1
)

copy "%PROJECT_ROOT%\installer\dist\%VARIANT_NAME%.toml" "%VARIANT_DIR%\dist.toml" >nul
if errorlevel 1 (
    echo ERROR: Failed to copy dist.toml to %VARIANT_NAME%
    exit /b 1
)

REM Copy documentation files if they exist
if exist "%PROJECT_ROOT%\README.md" (
    copy "%PROJECT_ROOT%\README.md" "%VARIANT_DIR%\README.md" >nul
)

if exist "%PROJECT_ROOT%\LICENSE" (
    copy "%PROJECT_ROOT%\LICENSE" "%VARIANT_DIR%\LICENSE" >nul
)

if exist "%PROJECT_ROOT%\version.txt" (
    copy "%PROJECT_ROOT%\version.txt" "%VARIANT_DIR%\version.txt" >nul
)

echo    %VARIANT_NAME% complete.
goto :eof
