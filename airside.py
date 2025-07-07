#!/usr/bin/env python3
import serial
import socket
import bluetooth
import threading
import subprocess
import time
import json
import os
from flask import Flask, render_template_string, request
from werkzeug.serving import make_server

# Configuration Manager
class AirsideConfig:
    CONFIG_FILE = 'airside_config.json'
    
    def __init__(self):
        self.settings = self.load_config()
        
    def load_config(self):
        defaults = {
            'uart_port': '/dev/ttyAMA0',
            'baud_rate': 115200,
            'wifi_mode': 'client',
            'ap_ssid': 'DroneAirside',
            'ap_password': 'dronepair',
            'paired_groundstations': [],
            'device_name': 'DroneUnit-' + os.popen('hostname').read().strip()
        }
        
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                return {**defaults, **json.load(f)}
        except:
            return defaults
    
    def save(self):
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(self.settings, f, indent=2)

# Web UI for standalone configuration
app = Flask(__name__)
config = AirsideConfig()

# HTML Template for Airside Config UI
CONFIG_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ config.device_name }} - Configuration</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h1 { color: #333; border-bottom: 1px solid #eee; padding-bottom: 10px; }
        .form-group { margin-bottom: 15px; }
        label { display: inline-block; width: 150px; font-weight: bold; }
        input, select { padding: 8px; width: 200px; border: 1px solid #ddd; border-radius: 4px; }
        button { background: #4CAF50; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; }
        button:hover { background: #45a049; }
        .status { margin-top: 20px; padding: 10px; border-radius: 4px; }
        .success { background: #dff0d8; color: #3c763d; }
        .error { background: #f2dede; color: #a94442; }
    </style>
</head>
<body>
    <div class="container">
        <h1>{{ config.device_name }} Configuration</h1>
        
        <form method="POST" action="/update">
            <div class="form-group">
                <label>Device Name:</label>
                <input type="text" name="device_name" value="{{ config.device_name }}" required>
            </div>
            
            <h2>Serial Configuration</h2>
            <div class="form-group">
                <label>UART Port:</label>
                <input type="text" name="uart_port" value="{{ config.uart_port }}" required>
            </div>
            <div class="form-group">
                <label>Baud Rate:</label>
                <input type="number" name="baud_rate" value="{{ config.baud_rate }}" required>
            </div>
            
            <h2>Network Configuration</h2>
            <div class="form-group">
                <label>WiFi Mode:</label>
                <select name="wifi_mode" id="wifi_mode" onchange="toggleApSettings()">
                    <option value="client" {% if config.wifi_mode == 'client' %}selected{% endif %}>Client</option>
                    <option value="ap" {% if config.wifi_mode == 'ap' %}selected{% endif %}>Access Point</option>
                </select>
            </div>
            
            <div id="ap_settings" style="{% if config.wifi_mode != 'ap' %}display:none{% endif %}">
                <div class="form-group">
                    <label>AP SSID:</label>
                    <input type="text" name="ap_ssid" value="{{ config.ap_ssid }}">
                </div>
                <div class="form-group">
                    <label>AP Password:</label>
                    <input type="password" name="ap_password" value="{{ config.ap_password }}">
                </div>
            </div>
            
            <button type="submit">Save Configuration</button>
        </form>
        
        {% if message %}
        <div class="status {{ message.type }}">{{ message.text }}</div>
        {% endif %}
    </div>
    
    <script>
        function toggleApSettings() {
            const apSettings = document.getElementById('ap_settings');
            apSettings.style.display = document.getElementById('wifi_mode').value === 'ap' ? 'block' : 'none';
        }
    </script>
</body>
</html>
"""

@app.route('/')
def config_ui():
    return render_template_string(CONFIG_HTML, config=config.settings)

@app.route('/update', methods=['POST'])
def update_config():
    config.settings.update({
        'device_name': request.form.get('device_name'),
        'uart_port': request.form.get('uart_port'),
        'baud_rate': int(request.form.get('baud_rate')),
        'wifi_mode': request.form.get('wifi_mode'),
        'ap_ssid': request.form.get('ap_ssid'),
        'ap_password': request.form.get('ap_password')
    })
    config.save()
    
    # Restart network services if needed
    if config.settings['wifi_mode'] == 'ap':
        setup_ap_mode()
    
    return render_template_string(CONFIG_HTML, config=config.settings, 
                                message={'type': 'success', 'text': 'Configuration saved successfully!'})

def setup_ap_mode():
    try:
        subprocess.run(['nmcli', 'con', 'down', 'hotspot'], check=True)
        subprocess.run(['nmcli', 'con', 'add', 'type', 'wifi', 'ifname', 'wlan0', 'con-name', 'hotspot',
                       'autoconnect', 'yes', 'ssid', config.settings['ap_ssid']], check=True)
        subprocess.run(['nmcli', 'con', 'modify', 'hotspot', '802-11-wireless.mode', 'ap',
                       '802-11-wireless.band', 'bg', 'ipv4.method', 'shared'], check=True)
        subprocess.run(['nmcli', 'con', 'modify', 'hotspot', 'wifi-sec.key-mgmt', 'wpa-psk',
                       'wifi-sec.psk', config.settings['ap_password']], check=True)
        subprocess.run(['nmcli', 'con', 'up', 'hotspot'], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error setting up AP mode: {e}")

# Connection Manager
class ConnectionHandler:
    def __init__(self):
        self.active = False
        self.thread = threading.Thread(target=self.monitor_connections, daemon=True)
        self.thread.start()
    
    def monitor_connections(self):
        while True:
            if not self.check_groundstation_connection():
                if config.settings['wifi_mode'] == 'ap':
                    setup_ap_mode()
                self.start_config_server()
            time.sleep(30)
    
    def check_groundstation_connection(self):
        # Implement your actual connection check logic here
        return False  # Simulating no connection
    
    def start_config_server(self):
        if not hasattr(self, 'server'):
            self.server = make_server('0.0.0.0', 80, app)
            threading.Thread(target=self.server.serve_forever, daemon=True).start()

# Main Airside Functionality
def airside_main():
    connection_handler = ConnectionHandler()
    
    # Initialize serial connection
    ser = serial.Serial(config.settings['uart_port'], config.settings['baud_rate'], timeout=1)
    
    # Main loop
    while True:
        if connection_handler.active:
            # Normal operation - forward telemetry
            data = ser.readline()
            if data:
                forward_data(data)
        time.sleep(0.1)

def forward_data(data):
    # Implement your data forwarding logic here
    pass

if __name__ == "__main__":
    airside_main()