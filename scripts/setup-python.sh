#!/bin/bash

# Check if .venv folder exists; if not, create it
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv..."
    python3 -m venv .venv
    
    # Upgrade pip and install requirements using the direct path
    ./.venv/bin/python -m pip install --upgrade pip
    ./.venv/bin/python -m pip install -r linux_requirements.txt
else
    echo "Virtual environment already exists."
fi

# Activate the virtual environment so it stays active in your current terminal
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "Python environment ready and activated!"
else
    echo "Error: Activation file not found."
fi