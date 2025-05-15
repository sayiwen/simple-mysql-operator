#!/bin/bash
set -e

# Check for Python 3.10
if command -v python3.10 &> /dev/null; then
    PYTHON_CMD="python3.10"
elif command -v python3 &> /dev/null && [[ $(python3 -c "import sys; print(sys.version_info.major == 3 and sys.version_info.minor >= 10)") == "True" ]]; then
    PYTHON_CMD="python3"
else
    echo "Error: Python 3.10 or newer is required but not found."
    echo "Please install Python 3.10 or newer before running this script."
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment with $PYTHON_CMD..."
$PYTHON_CMD -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip wheel

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

echo "Setup complete! You can now run the operator with:"
echo "  source venv/bin/activate"
echo "  # Run directly with kopf (recommended)"
echo "  kopf run src/main.py"
echo "  # OR run with Python"
echo "  python src/main.py" 