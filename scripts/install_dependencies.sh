#!/bin/bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-dev \
    libatlas-base-dev \
    libjasper-dev \
    libqtgui4 \
    libqt4-test \
    bluez \
    bluetooth

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python packages
pip install --upgrade pip
pip install -r requirements.txt

# Install GStreamer for Raspberry Pi if needed
if [[ $(uname -m) == "armv7l" ]]; then
    sudo apt-get install -y \
        gstreamer1.0-tools \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        libgstreamer-plugins-good1.0-dev
fi

echo "Installation complete. Activate virtual environment with: source venv/bin/activate"