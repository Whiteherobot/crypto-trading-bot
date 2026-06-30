@echo off
REM ============================================================
REM  Cryptobot - instalacion en Windows (doble clic)
REM ============================================================
echo === Cryptobot: creando entorno virtual e instalando dependencias ===

py -3.11 -m venv venv 2>nul || python -m venv venv
if not exist venv\Scripts\activate.bat (
    echo ERROR: no se pudo crear el venv. Instala Python 3.10-3.13 desde python.org
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo === Instalacion completa ===
echo Siguiente paso: copia .env.example a .env y pega tus claves de la Testnet
echo    copy .env.example .env
echo.
pause
