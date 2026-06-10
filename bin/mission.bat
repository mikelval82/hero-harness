@echo off
setlocal enabledelayedexpansion

set "HARNESS_HOME=%~dp0.."
set "HARNESS_PYTHON=%CLAUDE_HARNESS_PYTHON%"

REM Set PYTHONPATH to HARNESS_HOME to ensure src module is found
set "PYTHONPATH=%HARNESS_HOME%"

REM Load environment variables from .env.local (personal credentials)
if exist "%HARNESS_HOME%\.env.local" (
    for /f "tokens=1,2 delims==" %%A in ("%HARNESS_HOME%\.env.local") do (
        if not "%%A"=="" if not "%%A:~0,1%%" equ "#" (
            set "%%A=%%B"
        )
    )
)

REM Load environment variables from src\.env (shared configuration)
if exist "%HARNESS_HOME%\src\.env" (
    for /f "tokens=1,2 delims==" %%A in ("%HARNESS_HOME%\src\.env") do (
        if not "%%A"=="" if not "%%A:~0,1%%" equ "#" (
            set "%%A=%%B"
        )
    )
)

if not defined HARNESS_PYTHON (
    if exist "%HARNESS_HOME%\.venv\Scripts\python.exe" (
        set "HARNESS_PYTHON=%HARNESS_HOME%\.venv\Scripts\python.exe"
    )
)

if not defined HARNESS_PYTHON (
    set "HARNESS_PYTHON=python"
)

REM Change to HARNESS_HOME to ensure src module is found
cd /d "%HARNESS_HOME%"
"%HARNESS_PYTHON%" "src\cli.py" %*
