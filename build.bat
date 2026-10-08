@echo off
setlocal enabledelayedexpansion
title Download Manager - Build Pipeline

echo ============================================================
echo   Download Manager - Automated Build and Packaging Pipeline
echo ============================================================
echo.

REM 0. Terminate any running application instances to prevent locked files
taskkill /F /IM DownloadManager.exe >nul 2>&1

REM 1. Check Python Virtual Environment
if exist "venv\Scripts\activate.bat" (
    echo [Environment] Activating virtual environment: venv
    call venv\Scripts\activate.bat
) else (
    echo [Environment] venv not found, using system Python.
)

REM Parse command-line arguments
set "QUICK_MODE=0"
set "USER_VERSION="

:parse_args
if "%~1"=="" goto args_done
if "%~1"=="--installer-only" (
    set "QUICK_MODE=1"
    shift
    goto parse_args
)
if "%~1"=="--quick" (
    set "QUICK_MODE=1"
    shift
    goto parse_args
)
if "!USER_VERSION!"=="" (
    set "USER_VERSION=%~1"
    shift
    goto parse_args
)
shift
goto parse_args
:args_done

REM 2. Detect default version
set "DEFAULT_VERSION=1.1.0"
if exist "app\__init__.py" (
    for /f "tokens=2 delims==" %%v in ('findstr /i "__version__" app\__init__.py') do (
        set "TEMP_VER=%%v"
        set "TEMP_VER=!TEMP_VER: =!"
        set "TEMP_VER=!TEMP_VER:"=!"
        set "TEMP_VER=!TEMP_VER:'=!"
        if not "!TEMP_VER!"=="" set "DEFAULT_VERSION=!TEMP_VER!"
    )
)

REM 3. Prompt user for version
if "!USER_VERSION!"=="" (
    echo.
    echo ============================================================
    set /p USER_VERSION="Please enter application version [Default: !DEFAULT_VERSION!]: "
    echo ============================================================
)

if "!USER_VERSION!"=="" set "USER_VERSION=!DEFAULT_VERSION!"
echo.
echo [Version] Application version: !USER_VERSION!

REM 4. Synchronize version with source files and EXE metadata
python update_version.py !USER_VERSION!
if errorlevel 1 (
    echo [ERROR] Failed to update version.
    pause
    exit /b 1
)

if "!QUICK_MODE!"=="1" goto inno_step

REM 5. Generate Application Icon
echo.
echo [1/5] Preparing application icon: build_icon.py
python build_icon.py
if errorlevel 1 (
    echo [ERROR] Icon generation failed.
    pause
    exit /b 1
)

REM 6. Clean previous build artifacts and cache
echo.
echo [2/5] Cleaning old build artifacts...
if exist "build" rmdir /s /q "build"
if exist "dist\DownloadManager" rmdir /s /q "dist\DownloadManager"
if exist "dist\DownloadManagerSetup.exe" del /f /q "dist\DownloadManagerSetup.exe"

REM 7. Compile Python code to EXE using PyInstaller
echo.
echo [3/5] Building latest Python source with PyInstaller (v!USER_VERSION!)...
echo       Analyzing dependencies and creating executable, this may take a moment...
python -m PyInstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed!
    pause
    exit /b 1
)

if not exist "dist\DownloadManager\DownloadManager.exe" (
    echo.
    echo [ERROR] dist\DownloadManager\DownloadManager.exe not found!
    pause
    exit /b 1
)
echo       =^> DownloadManager.exe created successfully (v!USER_VERSION!).

:inno_step
REM 8. Build Windows installer package using Inno Setup
echo.
echo [4/5] Building installer package with Inno Setup (v!USER_VERSION!)...

set "ISCC="
if exist "C:\Program Files\Inno Setup 7\ISCC.exe"       set "ISCC=C:\Program Files\Inno Setup 7\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 7\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 7\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if "!ISCC!"=="" (
    where iscc >nul 2>&1
    if not errorlevel 1 set "ISCC=iscc"
)

if "!ISCC!"=="" (
    echo.
    echo [WARNING] Inno Setup compiler (ISCC.exe) not found.
    echo           Compiled application directory is ready: dist\DownloadManager\
    echo           Install Inno Setup to create an installer package.
    goto done
)

"!ISCC!" "/dMyAppVersion=!USER_VERSION!" installer\setup.iss
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to create Inno Setup installer package.
    pause
    exit /b 1
)
echo       =^> dist\DownloadManagerSetup.exe created successfully (v!USER_VERSION!).

REM 9. Synchronize Website Download Assets
echo.
echo [5/5] Synchronizing website download assets...
if exist "dist\DownloadManagerSetup.exe" (
    if exist "website\assets" (
        copy /y "dist\DownloadManagerSetup.exe" "website\assets\DownloadManagerSetup.exe" >nul
        echo       =^> website\assets\DownloadManagerSetup.exe updated!
    )
)

:done
echo.
echo ============================================================
echo   ALL BUILD TASKS COMPLETED SUCCESSFULLY!
echo ============================================================
echo  [Version Tag]        !USER_VERSION!
if exist "dist\DownloadManagerSetup.exe" (
    echo  [Installer Package]  dist\DownloadManagerSetup.exe
    if exist "website\assets\DownloadManagerSetup.exe" (
        echo  [Website Asset]      website\assets\DownloadManagerSetup.exe
    )
) else (
    echo  [App Directory]      dist\DownloadManager\
    echo  [Executable]         dist\DownloadManager\DownloadManager.exe
)
echo ============================================================
echo.
if "%1"=="" pause
