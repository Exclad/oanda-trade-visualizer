@echo off
setlocal
echo Ensuring we are in the script's directory...
REM This command changes the directory to the folder the .bat file is in
cd /d "%~dp0"

REM Define the name of the virtual environment folder
set VENV_NAME=venv

REM Check if the virtual environment's 'activate' script exists
if not exist "%VENV_NAME%\Scripts\activate" (
    echo.
    echo Virtual environment not found. Creating one...
    python -m venv %VENV_NAME%
    
    REM Check if venv creation failed
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        echo Please ensure Python is installed and added to your PATH.
        pause
        exit /b 1
    )
    
    echo.
    echo Activating virtual environment...
    call "%VENV_NAME%\Scripts\activate.bat"
    
    echo.
    echo Installing dependencies from requirements.txt...
    pip install -r requirements.txt
    
    REM Check if installation failed
    if %errorlevel% neq 0 (
        echo ERROR: Dependency installation failed. Please check requirements.txt
        echo and your internet connection.
        pause
        exit /b 1
    )
    echo Installation complete.

) else (
    echo.
    echo Virtual environment found. Activating...
    call "%VENV_NAME%\Scripts\activate.bat"
)

echo.
echo Starting Oanda Trading Dashboard...
echo (To stop, press Ctrl+C in this window)
echo.
streamlit run main.py

echo.
echo Dashboard has been closed.
pause
endlocal
