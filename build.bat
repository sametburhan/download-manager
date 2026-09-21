@echo off
setlocal enabledelayedexpansion
title Download Manager - Build Pipeline

echo ============================================================
echo   Download Manager - Otomatik Derleme ve Paketleme
echo ============================================================
echo.

REM 0. Kilitli dosyalari onlemek icin acik uygulamayi kapat
taskkill /F /IM DownloadManager.exe >nul 2>&1

REM 1. Python Sanal Ortami Kontrolu
if exist "venv\Scripts\activate.bat" (
    echo [Ortam] Sanal ortam etkinlestiriliyor: venv
    call venv\Scripts\activate.bat
) else (
    echo [Ortam] venv bulunamadi, sistem Python kullanilacak.
)

REM Argumanlari ayristir
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

REM 2. Varsayilan versiyonu tespit et
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

REM 3. Kullanicidan Versiyon Bilgisi Isteme
if "!USER_VERSION!"=="" (
    echo.
    echo ============================================================
    set /p USER_VERSION="Lutfen uygulama versiyonunu girin [Varsayilan: !DEFAULT_VERSION!]: "
    echo ============================================================
)

if "!USER_VERSION!"=="" set "USER_VERSION=!DEFAULT_VERSION!"
echo.
echo [Versiyon] Uygulama versiyonu: !USER_VERSION!

REM 4. Versiyonu Kod Dosyalarina ve EXE Bilgisine Senkronize Et
python update_version.py !USER_VERSION!
if errorlevel 1 (
    echo [HATA] Versiyon guncelleme basarisiz oldu.
    pause
    exit /b 1
)

if "!QUICK_MODE!"=="1" goto inno_step

REM 5. Ikon Olusturma
echo.
echo [1/5] Uygulama ikonu hazirlaniyor: build_icon.py
python build_icon.py
if errorlevel 1 (
    echo [HATA] Ikon donusturme islemi basarisiz oldu.
    pause
    exit /b 1
)

REM 6. Eski Derleme ve Onbellek Temizligi
echo.
echo [2/5] Eski derleme kalintilari temizleniyor...
if exist "build" rmdir /s /q "build"
if exist "dist\DownloadManager" rmdir /s /q "dist\DownloadManager"
if exist "dist\DownloadManagerSetup.exe" del /f /q "dist\DownloadManagerSetup.exe"

REM 7. PyInstaller ile Yeni Python Kodlarinin EXE Olarak Derlenmesi
echo.
echo [3/5] Guncel Python kodlari PyInstaller ile derleniyor (v!USER_VERSION!)...
echo       Kaynak kodlar taranip EXE olusturuluyor, bu islem biraz surebilir...
python -m PyInstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [HATA] PyInstaller derleme islemi basarisiz oldu!
    pause
    exit /b 1
)

if not exist "dist\DownloadManager\DownloadManager.exe" (
    echo.
    echo [HATA] dist\DownloadManager\DownloadManager.exe bulunamadi!
    pause
    exit /b 1
)
echo       =^> Guncel DownloadManager.exe basariyla olusturuldu (v!USER_VERSION!).

:inno_step
REM 8. Inno Setup ile Windows Kurulum Paketinin Olusturulmasi
echo.
echo [4/5] Inno Setup ile kurulum paketi derleniyor (v!USER_VERSION!)...

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
    echo [UYARI] Inno Setup bulunamadi.
    echo         Derlenen guncel uygulama klasoru hazir: dist\DownloadManager\
    echo         Installer olusturmak icin Inno Setup kurabilirsiniz.
    goto done
)

"!ISCC!" "/dMyAppVersion=!USER_VERSION!" installer\setup.iss
if errorlevel 1 (
    echo.
    echo [HATA] Inno Setup kurulum paketi olusturulamadi.
    pause
    exit /b 1
)
echo       =^> dist\DownloadManagerSetup.exe basariyla olusturuldu (v!USER_VERSION!).

REM 9. Web Sitesi Indirme Dosyasinin Guncellenmesi
echo.
echo [5/5] Web sitesi indirme dosyasi senkronize ediliyor...
if exist "dist\DownloadManagerSetup.exe" (
    if exist "website\assets" (
        copy /y "dist\DownloadManagerSetup.exe" "website\assets\DownloadManagerSetup.exe" >nul
        echo       =^> website\assets\DownloadManagerSetup.exe guncellendi!
    )
)

:done
echo.
echo ============================================================
echo   TUM DERLEME ISLEMLERI BASARIYLA TAMAMLANDI!
echo ============================================================
echo  [Versiyon Etiketi] !USER_VERSION!
if exist "dist\DownloadManagerSetup.exe" (
    echo  [Kurulum Dosyasi] dist\DownloadManagerSetup.exe
    if exist "website\assets\DownloadManagerSetup.exe" (
        echo  [Web Dagitimi]   website\assets\DownloadManagerSetup.exe
    )
) else (
    echo  [Uygulama Dizini] dist\DownloadManager\
    echo  [Calistirilabilir] dist\DownloadManager\DownloadManager.exe
)
echo ============================================================
echo.
if "%1"=="" pause
