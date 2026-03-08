@echo off
REM Start Ghost with the supervisor (recommended)
REM Usage: start.bat [--api-key sk-or-...]

setlocal

set "GHOST_DIR=%~dp0"
set "GHOST_HOME=%USERPROFILE%\.ghost"

REM Use virtual environment if it exists
if exist "%GHOST_DIR%.venv\Scripts\activate.bat" (
    call "%GHOST_DIR%.venv\Scripts\activate.bat"
)

REM Check if Ghost is already running via supervisor PID
if exist "%GHOST_HOME%\supervisor.pid" (
    set /p PID=<"%GHOST_HOME%\supervisor.pid"
    tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul 2>&1
    if not errorlevel 1 (
        echo Ghost is already running (supervisor PID %PID%^)
        echo Dashboard: http://localhost:3333
        echo To stop: stop.bat
        exit /b 0
    )
)

REM Check if Ghost is already running via daemon PID
if exist "%GHOST_HOME%\ghost.pid" (
    set /p PID=<"%GHOST_HOME%\ghost.pid"
    tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul 2>&1
    if not errorlevel 1 (
        echo Ghost is already running (PID %PID%^) without supervisor.
        echo Dashboard: http://localhost:3333
        echo To stop: stop.bat
        exit /b 0
    )
)

python "%GHOST_DIR%ghost_supervisor.py" %*
