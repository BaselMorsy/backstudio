@echo off
REM BackStudio Startup Script for Windows
REM Starts both backend and frontend servers

echo ========================================
echo    BackStudio Startup Script
echo ========================================
echo.

REM Get package manager from setup
set PACKAGE_MANAGER=pip
if exist .package_manager (
    set /p PACKAGE_MANAGER=<.package_manager
)

echo Package manager: %PACKAGE_MANAGER%
echo.

REM Create logs directory
if not exist "logs" mkdir logs

REM Start backend based on package manager
echo Starting backend server...

if "%PACKAGE_MANAGER%"=="pip" (
    REM Activate venv and start backend
    call venv\Scripts\activate.bat
    start "BackStudio Backend" /B python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 > logs\backend.log 2>&1
    
) else if "%PACKAGE_MANAGER%"=="conda" (
    REM Use conda environment
    call conda activate backstudio
    start "BackStudio Backend" /B python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 > logs\backend.log 2>&1
)

echo [OK] Backend started

REM Wait a moment for backend to start
timeout /t 2 /nobreak >nul

REM Start frontend
echo Starting frontend server...
cd frontend
start "BackStudio Frontend" /B npm run dev -- --host 0.0.0.0 > ..\logs\frontend.log 2>&1
cd ..

echo [OK] Frontend started
echo.

echo ========================================
echo    BackStudio is Running!
echo ========================================
echo.
echo Access points:
echo   Frontend:     http://localhost:5173
echo   Backend API:  http://localhost:8000
echo   API Docs:     http://localhost:8000/docs
echo.
echo Logs:
echo   Backend:  logs\backend.log
echo   Frontend: logs\frontend.log
echo.
echo Press any key to stop both servers...
pause >nul

REM Stop servers
echo.
echo Shutting down servers...
taskkill /FI "WindowTitle eq BackStudio Backend*" /F >nul 2>&1
taskkill /FI "WindowTitle eq BackStudio Frontend*" /F >nul 2>&1
echo [OK] Servers stopped
