@echo off
cd /d "%~dp0"
if exist ".tools\python\python.exe" (
  ".tools\python\python.exe" app.py
) else if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  echo Python environment not found. Follow README.md setup instructions.
  pause
)
if errorlevel 1 pause
