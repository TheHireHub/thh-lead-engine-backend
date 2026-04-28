@echo off
REM THH Lead Engine Backend — first-time bootstrap (Windows cmd.exe).
REM Re-run safely; every step is idempotent.

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ==^> checking python
where python >nul 2>&1 || (echo python not found on PATH & exit /b 1)

echo ==^> creating .venv (if missing)
if not exist .venv (
  python -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat || exit /b 1

echo ==^> installing requirements
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt || exit /b 1

echo ==^> checking .env
if not exist .env (
  copy /Y env.example .env >nul
  echo .env created from env.example — edit it now with real MySQL creds + secrets
  echo press ENTER once you've edited .env, or Ctrl+C to abort
  pause >nul
)

echo ==^> running setup_database.py
python setup_database.py || exit /b 1

echo ==^> stamping Alembic at head
dir /b alembic\versions 2>nul | findstr /v ".gitkeep" >nul
if errorlevel 1 (
  alembic revision --autogenerate -m "baseline" 2>nul
)
alembic stamp head || exit /b 1

echo ==^> smoke-importing app.py
python -c "import app; print(f'registered {len(app.app.routes)} routes')" || exit /b 1

echo.
echo Bootstrap complete.
echo.
echo Next steps:
echo   .venv\Scripts\activate.bat
echo   uvicorn app:app --reload --port 5050
echo   (separate shell)  arq workers.settings.WorkerSettings
echo   docs at http://localhost:5050/docs
endlocal
