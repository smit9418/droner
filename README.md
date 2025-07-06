# Drone Ground Station System

![Drone Ground Station Demo](docs/demo-screenshot.png)

A cross-platform drone telemetry and video streaming system for Raspberry Pi and Windows. Supports Matek flight controllers, ExpressLRS, Taranis QX7, and provides a web-based UI accessible from any device.

## Features

- 🚁 Real-time flight telemetry display
- 📹 Video streaming with telemetry overlay
- 🌐 Web-based UI for phones/laptops
- 🖥️ Touchscreen interface for Raspberry Pi
- 📡 Multiple connectivity options:
  - WiFi
  - Bluetooth
  - ExpressLRS (900MHz)
- 🛩️ Supports:
  - Matek F722-SE Flight Controller
  - Taranis QX7 transmitter
  - ExpressLRS modules
- 🧩 Preset-based UI configurations
- 🗺️ GPS map integration
- ⚙️ Cross-platform (Windows & Raspberry Pi)

## Hardware Setup

### Airside Components
- Raspberry Pi Zero W 2
- Matek F722-SE Flight Controller
- ExpressLRS module
- Camera system

### Ground Station
- Raspberry Pi 4 B+
- 7" Touchscreen
- Taranis QX7 transmitter
- TriplePlay RC 5.8GHz Video Receiver
- USB to RCA capture adapter

## Installation

### Prerequisites
- Python 3.7+
- Pip package manager

```bash
# Clone repository
git clone https://github.com/smit9418/droner.git
cd droner

# Install dependencies
pip install -r requirements.txt