@echo off
REM BackStudio Setup Script for Windows
REM Supports pip and conda for Python dependency management

echo ========================================
echo    BackStudio Setup Script (Windows)
echo ========================================
echo.

REM Check for Node.js
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js is not installed
    echo Please install Node.js 16+ from https://nodejs.org/
    pause
    exit /b 1
)
echo [OK] Node.js is installed
node --version

REM Check for Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed
    echo Please install Python 3.11+ from https://www.python.org/
    pause
    exit /b 1
)
echo [OK] Python is installed
python --version
echo.

REM Ask user which package manager to use
echo Choose Python package manager:
echo   1) pip (recommended for Windows)
echo   2) conda (if using Anaconda/Miniconda)
echo.
set /p pm_choice="Enter choice [1-2]: "

if "%pm_choice%"=="1" (
    set PACKAGE_MANAGER=pip
) else if "%pm_choice%"=="2" (
    set PACKAGE_MANAGER=conda
) else (
    echo Invalid choice. Defaulting to pip.
    set PACKAGE_MANAGER=pip
)

echo.
echo Setting up Python environment with %PACKAGE_MANAGER%...

if "%PACKAGE_MANAGER%"=="pip" (
    REM Create virtual environment if it doesn't exist
    if not exist "venv" (
        echo Creating virtual environment...
        python -m venv venv
    )
    
    REM Activate virtual environment
    call venv\Scripts\activate.bat
    
    REM Upgrade pip
    python -m pip install --upgrade pip
    
    REM Install dependencies
    echo Installing Python dependencies...
    pip install -r backend\requirements.txt
    
    echo [OK] Python environment ready (pip)
    
) else if "%PACKAGE_MANAGER%"=="conda" (
    REM Check if conda is installed
    where conda >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] conda is not installed
        echo Please install Anaconda or Miniconda
        pause
        exit /b 1
    )
    
    REM Check if environment exists
    conda env list | findstr "backstudio" >nul
    if %ERRORLEVEL% EQU 0 (
        echo backstudio environment already exists
        call conda activate backstudio
    ) else (
        echo Creating conda environment...
        call conda create -n backstudio python=3.11 -y
        call conda activate backstudio
    )
    
    REM Install dependencies
    echo Installing Python dependencies...
    pip install -r backend\requirements.txt
    
    echo [OK] Python environment ready (conda)
)

REM Save package manager choice
echo %PACKAGE_MANAGER% > .package_manager

echo.
echo Installing frontend dependencies...
cd frontend

if not exist "node_modules" (
    echo Running npm install...
    call npm install
) else (
    echo Dependencies already installed
)

echo [OK] Frontend dependencies ready
cd ..

REM Create necessary directories
echo.
echo Creating project directories...
if not exist "workspace" mkdir workspace
if not exist "logs" mkdir logs
echo [OK] Directories created

echo.
echo ========================================
echo    Setup Complete!
echo ========================================
echo.
echo Package manager: %PACKAGE_MANAGER%
echo.
echo Next steps:
echo   1. Run start.bat to start BackStudio
echo   2. Open http://localhost:5173 in your browser
echo   3. Check http://localhost:8000/docs for API documentation
echo.

if "%PACKAGE_MANAGER%"=="conda" (
    echo Note: For conda, activate the environment first:
    echo   conda activate backstudio
    echo.
)

pause
