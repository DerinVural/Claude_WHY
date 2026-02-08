@echo off
REM GC-RAG-VIVADO Resume Training Script
REM Bilgisayar açıldığında kaldığı yerden devam eder

echo ========================================
echo   GC-RAG-VIVADO Resume Training
echo ========================================
echo.

cd /d "C:\Users\murat\Documents\GitHub\GC-RAG-VIVADO-2"

REM Python encoding ayarla
set PYTHONIOENCODING=utf-8

REM Eğitime devam et
echo Egitim baslatiliyor...
python scripts/train_resume.py

echo.
echo Islem tamamlandi!
pause
