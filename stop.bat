@echo off
REM Stop the Ghost system (supervisor + daemon)
REM Usage: stop.bat

setlocal

set "GHOST_HOME=%USERPROFILE%\.ghost"
set "stopped=false"

if exist "%GHOST_HOME%\supervisor.pid" (
    set /p PID=<"%GHOST_HOME%\supervisor.pid"
    tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul 2>&1
    if not errorlevel 1 (
        taskkill /PID %PID% /F >nul 2>&1
        echo Supervisor (PID %PID%^) stopped.
        set "stopped=true"
    )
    del /f "%GHOST_HOME%\supervisor.pid" >nul 2>&1
)

if exist "%GHOST_HOME%\ghost.pid" (
    set /p PID=<"%GHOST_HOME%\ghost.pid"
    tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul 2>&1
    if not errorlevel 1 (
        taskkill /PID %PID% /F >nul 2>&1
        echo Ghost (PID %PID%^) stopped.
        set "stopped=true"
    )
    del /f "%GHOST_HOME%\ghost.pid" >nul 2>&1
)

if "%stopped%"=="false" (
    echo Ghost is not running.
)
