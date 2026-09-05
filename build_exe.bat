@echo off
echo ================================================================
echo Building Crypto90's CryptoPad Executable
echo ================================================================

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

pyinstaller --onefile --noconsole --name "CryptoPad" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    CryptoPad.py

echo.
echo ================================================================
echo Build complete! Your standalone executable is located in:
echo   dist\CryptoPad.exe
echo ================================================================
pause
