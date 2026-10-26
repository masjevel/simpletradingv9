@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto fail
)
if not exist ".venv\ready.txt" (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto fail
    echo OK>".venv\ready.txt"
)
".venv\Scripts\python.exe" -m streamlit run app.py --server.address localhost --browser.gatherUsageStats false
if errorlevel 1 goto fail
exit /b 0
:fail
echo.
echo Appen kunde inte starta. Kontrollera att Python 3.11-3.13 ar installerat
echo och att internet fungerar. Las felmeddelandet ovan.
pause
exit /b 1
