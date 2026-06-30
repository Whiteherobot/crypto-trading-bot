@echo off
REM Lanza el dashboard de control (Windows). Abre http://localhost:8501
call venv\Scripts\activate.bat
streamlit run dashboard.py
pause
