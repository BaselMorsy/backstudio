@echo off
REM Installs the `backstudio` CLI globally on PATH (Windows).
REM
REM Uses `uv tool install`, which puts backstudio in its own isolated
REM environment (separate from `uv sync`'s project-local .venv, which is for
REM BackStudio's own contributors/developers) and links its console script
REM onto a directory uv keeps on PATH.
setlocal

echo Installing BackStudio (backstudio CLI)...

where uv >nul 2>nul
if errorlevel 1 (
    echo uv not found - installing it first...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo Failed to install uv. Install it manually: https://docs.astral.sh/uv/
        exit /b 1
    )
    REM uv's own installer updates PATH via the registry, which only takes
    REM effect in a NEW shell - add it here too so this script can use uv
    REM immediately without asking the user to restart first.
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

cd /d "%~dp0"

REM Pinned to 3.11 to match .python-version (the primary/tested interpreter) -
REM Python 3.12 is also supported (see docs-site/getting-started/installation.md)
REM if you'd rather use `uv tool install --editable . --python 3.12` yourself.
uv tool install --editable . --python 3.11
if errorlevel 1 (
    echo Installation failed.
    exit /b 1
)

echo.
echo Done. The 'backstudio' command should now be on your PATH.
echo Try: backstudio --help
echo If that doesn't work yet, close and reopen your terminal and try again.
