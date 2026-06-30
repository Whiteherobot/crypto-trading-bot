@echo off
REM Lanza el bot de paper trading (Windows). Dejar esta ventana abierta.
call venv\Scripts\activate.bat
python -m live.paper_trade
pause
