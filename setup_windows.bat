@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.10 --version
if errorlevel 1 (
  echo Требуется установленный Python 3.10 и Python Launcher.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3.10 -m venv .venv
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -c "import sys; assert sys.version_info[:2] == (3, 10), 'Удалите только .venv и запустите установку заново: нужен Python 3.10'"
if errorlevel 1 (
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)
if not exist ".env" copy .env.example .env >nul
echo Готово. Откройте start_dashboard.bat
pause
