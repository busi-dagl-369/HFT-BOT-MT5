#!/bin/bash
# Run HFT-BOT Trading System
# Supports multiple environments: backtest, paper, live

set -e

# Get environment
ENV="${1:-backtest}"
echo "Starting HFT-BOT Trading System in $ENV mode..."

# Set environment variables
export TRADING_ENV="$ENV"
export LOG_LEVEL="INFO"
export LOGGING_BACKEND="zeromq"

# Ensure Python environment
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Run system
echo "Running HFT-BOT Trading System..."
python3 run_system.py

deactivate
