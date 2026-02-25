@echo off
REM ============================================================================
REM GCP-RAG-VIVADO Organized Training Script
REM VS Code dışında çalıştırılması önerilen eğitim scripti
REM ============================================================================

echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║           GCP-RAG-VIVADO ORGANIZED TRAINER                   ║
echo ║         Kategorilere Gore Organize Egitim Araci              ║
echo ╚═══════════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

REM Python kontrol
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Python bulunamadi!
    pause
    exit /b 1
)

REM Parametre kontrolü
if "%1"=="--list" (
    echo Kategoriler listeleniyor...
    python scripts/train_organized.py --list
    goto :end
)

if "%1"=="--stats" (
    echo Istatistikler gosteriliyor...
    python scripts/train_organized.py --stats
    goto :end
)

if "%1"=="--reset" (
    echo Sifirdan baslaniyor...
    python scripts/train_organized.py --reset
    goto :end
)

if not "%1"=="" (
    echo Kategori egitiliyor: %1
    python scripts/train_organized.py --category %1
    goto :end
)

REM Normal eğitim
echo Egitim baslatiliyor (kaldiginiz yerden devam edecek)...
echo.
echo [IPUCU] Durdurmak icin Ctrl+C basin.
echo [IPUCU] Program otomatik checkpoint kaydeder.
echo.
python scripts/train_organized.py

:end
echo.
echo Islem tamamlandi.
pause
