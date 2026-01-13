@echo off
REM BackStudio Stop Script for Windows
REM Stops both backend and frontend servers

echo ========================================
echo   Stopping BackStudio Servers
echo ========================================
echo.

REM Stop backend (port 8000)
echo Stopping backend (port 8000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo [OK] Backend stopped
echo.

REM Stop frontend (port 5173)
echo Stopping frontend (port 5173)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo [OK] Frontend stopped
echo.

echo ========================================
echo   All servers stopped
echo ========================================
echo.
pause
