#!/bin/bash

echo "Ensuring we are in the script's directory..."
# This command changes the directory to the folder the .sh file is in
cd "$(dirname "$0")"

# Define the name of the virtual environment folder
VENV_NAME="venv"

# Check if the virtual environment's 'activate' script exists
# Note: Mac/Linux use 'bin/activate' not 'Scripts\activate'
if [ ! -f "$VENV_NAME/bin/activate" ]; then
    echo
    echo "Virtual environment not found. Creating one..."
    # Use python3 as the standard for modern Mac/Linux
    python3 -m venv "$VENV_NAME"
    
    # Check if venv creation failed
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment."
        echo "Please ensure Python 3 is installed."
        read -p "Press [Enter] to exit."
        exit 1
    fi
    
    echo
    echo "Activating virtual environment..."
    # Use 'source' to activate in shell
    source "$VENV_NAME/bin/activate"
    
    echo
    echo "Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
    
    # Check if installation failed
    if [ $? -ne 0 ]; then
        echo "ERROR: Dependency installation failed. Please check requirements.txt"
        echo "and your internet connection."
        read -p "Press [Enter] to exit."
        exit 1
    fi
    echo "Installation complete."

else
    echo
    echo "Virtual environment found. Activating..."
    source "$VTCP_NAME/bin/activate"
fi

echo
echo "Starting Oanda Trading Dashboard..."
echo "(To stop, press Ctrl+C in this window)"
echo
streamlit run main.py

echo
echo "Dashboard has been closed."
read -p "Press [Enter] to exit."
