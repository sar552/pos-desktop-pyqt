@echo off
REM ============================================================
REM  POKIZA POS  —  Windows build skripti
REM  Windows mashinasida ishga tushiring (Python 3.10+ kerak).
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === [1/4] Virtual muhit (venv) ===
if not exist "venv\Scripts\python.exe" (
    py -3 -m venv venv || python -m venv venv
)
call venv\Scripts\activate.bat

echo.
echo === [2/4] Kutubxonalar o'rnatish ===
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo XATO: kutubxonalar o'rnatilmadi.
    pause
    exit /b 1
)

echo.
echo === [3/4] Eski build tozalash ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo === [4/4] Build (PyInstaller) ===
pyinstaller --noconfirm pos.spec
if errorlevel 1 (
    echo XATO: build muvaffaqiyatsiz.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  TAYYOR!
echo  Dastur:  dist\POKIZA-POS\POKIZA-POS.exe
echo.
echo  Butun "dist\POKIZA-POS" papkasini kassa kompyuteriga
echo  ko'chiring va POKIZA-POS.exe ni ishga tushiring.
echo ============================================================
pause
