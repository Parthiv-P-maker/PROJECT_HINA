@echo off
REM ---------------------------------------------------------------
REM  Hina test runner.  Double-click it, or run:  run_tests.bat
REM    run_tests.bat            -> everything (about 10 seconds)
REM    run_tests.bat quick      -> everything except the GUI window test
REM    run_tests.bat gui        -> only the GUI smoke test
REM    run_tests.bat -k parser  -> anything else is passed straight to pytest
REM  Tests never open real apps, speak, hit the network or change your
REM  memory/user_profile.json.
REM ---------------------------------------------------------------
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH.
    goto :end
)

python -c "import pytest" >nul 2>nul
if errorlevel 1 (
    echo Installing pytest ^(one time^)...
    python -m pip install pytest
)

if /I "%~1"=="quick" (
    python -m pytest tests -q --ignore=tests/test_gui_smoke.py
) else if /I "%~1"=="gui" (
    python -m pytest tests/test_gui_smoke.py -v
) else (
    python -m pytest tests -q %*
)

:end
echo.
if "%CI%"=="" pause
