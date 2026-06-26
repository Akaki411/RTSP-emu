@echo off

cd ../

echo Check Python installation...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python is not installed
    exit /b 1
)

echo Python version check...
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MINOR=%%b
)
if %PYTHON_MINOR% LSS 10 (
    echo The old version of Python is installed. Install the version no lower than 3.10
    exit /b 1
)


cls
echo Checking the virtual environment...
if not exist "venv\" (
    echo Creating a virtual environment...
    call python -m venv venv
)

echo Activating the virtual environment...
call .\venv\Scripts\activate.bat


cls
echo Installing dependencies...
call pip install -r requirements.txt

if errorlevel 1 (
    echo [ERROR] Dependency install error
    pause
    pause & exit /b 1
)

cls
python emulator.py

if errorlevel 1 (
    echo [ERROR] Start error
    pause
    pause & exit /b 1
)