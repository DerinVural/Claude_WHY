@echo off
echo ========================================
echo ChromaDB Yeniden Kurulum
echo ========================================
echo.

echo 1. ChromaDB klasoru siliniyor...
rmdir /s /q "chroma_db" 2>nul
echo    OK

echo.
echo 2. ChromaDB paketi kaldiriliyor...
pip uninstall -y chromadb chromadb-client

echo.
echo 3. ChromaDB yeniden kuruluyor...
pip install --no-cache-dir chromadb

echo.
echo 4. ChromaDB klasoru olusturuluyor...
mkdir "chroma_db"

echo.
echo ========================================
echo Tamamlandi!
echo ========================================
echo.
echo Simdi test edin:
echo   python scripts/test_chromadb.py
echo.
pause
