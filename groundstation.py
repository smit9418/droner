#!/usr/bin/env python3
# groundstation.py - Advanced Drone Ground Station
import sys
import json
import socket
import serial
import threading
import numpy as np
import cv2
import pygame
import os
import datetime
from flask import Flask, Response, render_template, request, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from pymavlink import mavutil
from werkzeug.security import generate_password_hash, check_password_hash

# Platform-specific configurations
IS_WINDOWS = sys.platform == 'win32'
IS_RASPBERRY = 'linux' in sys.platform and 'raspberrypi' in sys.uname().release.lower()

# Initialize Flask
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this in production!

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User database (in production, use a real database)
users = {
    'admin': {
        'password': generate_password_hash('adminpass'),
        'role': 'admin'
    },
    'viewer': {
        'password': generate_password_hash('viewerpass'),
        'role': 'viewer'
    }
}

class User(UserMixin):
    pass

@login_manager.user_loader
def user_loader(username):
    if username not in users:
        return
    user = User()
    user.id = username
    return user

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username in users and check_password_hash(users[username]['password'], password):
            user = User()
            user.id = username
            login_user(user)
            return redirect(url_for('index'))
        
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Global state
telemetry_data = {
    "altitude": 0, 
    "speed": 0, 
    "battery": 0, 
    "gps": (0, 0), 
    "mode": "MANUAL",
    "heading": 0,
    "satellites": 0
}
ui_preset = "dashboard"
recording = False
osd_enabled = True
current_camera = 0
recorded_flights = []
flight_history = {}

# Create recordings directory
if not os.path.exists('recordings'):
    os.makedirs('recordings')

def get_serial_ports():
    """Detect available serial ports"""
    ports = []
    if IS_WINDOWS:
        for i in range(1, 20):
            try:
                s = serial.Serial(f"COM{i}")
                ports.append(f"COM{i}")
                s.close()
            except: 
                pass
    else:
        ports = ["/dev/ttyACM0", "/dev/ttyAMA0", "/dev/ttyUSB0", "/dev/serial0"]
    return ports

def video_stream_generator():
    """Video streaming generator function"""
    cap = None
    
    # Try to open camera
    try:
        cap = cv2.VideoCapture(current_camera)
    except:
        pass
    
    if cap is None or not cap.isOpened():
        print("⚠️ Video capture not available!")
        while True:
            # Create a blank image with error message
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, "NO VIDEO SIGNAL", (100, 240), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            _, jpeg = cv2.imencode('.jpg', img)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
    
    # Initialize video writer if recording
    recorder = None
    telemetry_log = []
    recording_start = None
    
    while True:
        ret, frame = cap.read()
        if ret:
            # Add OSD overlay if enabled
            if osd_enabled:
                cv2.putText(frame, f"ALT: {telemetry_data['altitude']}m", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"SPD: {telemetry_data['speed']}km/h", (10, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"BAT: {telemetry_data['battery']}%", (10, 90), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"MODE: {telemetry_data['mode']}", (10, 120), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Record frame if recording
            if recording:
                if recorder is None:
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"recordings/flight_{timestamp}.mp4"
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    recorder = cv2.VideoWriter(filename, fourcc, 20.0, 
                                             (frame.shape[1], frame.shape[0]))
                    recording_start = datetime.datetime.now()
                    telemetry_log = []
                
                recorder.write(frame)
                # Log telemetry with timestamp
                telemetry_log.append({
                    'timestamp': (datetime.datetime.now() - recording_start).total_seconds(),
                    'data': telemetry_data.copy()
                })
            
            _, jpeg = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        else:
            # Create error frame if capture fails
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, "VIDEO ERROR", (100, 240), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            _, jpeg = cv2.imencode('.jpg', img)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
    
    if recorder:
        recorder.release()
        # Save telemetry log
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"recordings/telemetry_{timestamp}.json", 'w') as f:
            json.dump(telemetry_log, f)
        
        # Add to flight history
        flight_id = f"flight_{timestamp}"
        flight_history[flight_id] = {
            'video': f"recordings/flight_{timestamp}.mp4",
            'telemetry': f"recordings/telemetry_{timestamp}.json",
            'date': timestamp
        }
        recorded_flights.append(flight_id)

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(video_stream_generator(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/telemetry')
def telemetry_endpoint():
    """Telemetry data endpoint"""
    return json.dumps(telemetry_data)

@app.route('/set_preset', methods=['POST'])
@login_required
def set_preset():
    """Set UI preset"""
    global ui_preset
    data = request.json
    ui_preset = data.get('preset', 'dashboard')
    return "OK"

@app.route('/toggle_osd', methods=['POST'])
@login_required
def toggle_osd():
    """Toggle OSD display"""
    global osd_enabled
    osd_enabled = not osd_enabled
    return json.dumps({'status': 'success', 'osd_enabled': osd_enabled})

@app.route('/switch_camera', methods=['POST'])
@login_required
def switch_camera():
    """Switch camera source"""
    global current_camera
    current_camera = (current_camera + 1) % 3  # Cycle through 3 cameras
    return json.dumps({'status': 'success', 'camera': current_camera})

@app.route('/toggle_recording', methods=['POST'])
@login_required
def toggle_recording():
    """Start/stop flight recording"""
    global recording
    recording = not recording
    return json.dumps({'status': 'success', 'recording': recording})

@app.route('/send_command', methods=['POST'])
@login_required
def send_command():
    """Send command to drone"""
    if current_user.id != 'admin':
        return json.dumps({'status': 'error', 'message': 'Permission denied'}), 403
    
    command = request.json.get('command')
    # Here you would send actual commands to the drone via MAVLink
    print(f"Sending command: {command}")
    return json.dumps({'status': 'success', 'command': command})

@app.route('/flights')
@login_required
def list_flights():
    """List recorded flights"""
    return json.dumps({'flights': recorded_flights})

@app.route('/flight/<flight_id>')
@login_required
def get_flight(flight_id):
    """Get flight data"""
    if flight_id in flight_history:
        return json.dumps(flight_history[flight_id])
    return json.dumps({'status': 'error', 'message': 'Flight not found'}), 404

@app.route('/')
@login_required
def index():
    """Main UI interface"""
    return render_template('index.html', user_role=users[current_user.id]['role'])

@app.route('/settings')
@login_required
def settings():
    """Settings page (admin only)"""
    if users[current_user.id]['role'] != 'admin':
        return redirect(url_for('index'))
    return render_template('settings.html')

def handle_taranis():
    """Process Taranis QX7 input"""
    while True:
        ports = get_serial_ports()
        for port in ports:
            try:
                taranis = serial.Serial(port, 57600, timeout=1)
                print(f"📡 Connected to Taranis at {port}")
                while True:
                    data = taranis.readline()
                    # Process RC commands
                    if b'CH' in data:
                        try:
                            channels = {}
                            parts = data.decode().strip().split(',')
                            for part in parts:
                                if ':' in part:
                                    ch, val = part.split(':')
                                    channels[ch] = int(val)
                            telemetry_data['rc'] = channels
                        except Exception as e:
                            print(f"Error processing Taranis data: {str(e)}")
            except Exception as e:
                print(f"❌ Taranis error on {port}: {str(e)}")
                sleep(1)

def handle_telemetry():
    """Receive and process telemetry data"""
    # UDP for MAVLink/INAV
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', 14550))
    sock.settimeout(1.0)
    
    elrs = None
    
    while True:
        # UDP telemetry
        try:
            data, _ = sock.recvfrom(1024)
            # Parse MAVLink/INAV
            if b'GPS' in data:
                # Extract GPS data
                pass
            # Simulate telemetry updates
            telemetry_data['altitude'] = (telemetry_data['altitude'] + 0.1) % 100
            telemetry_data['speed'] = (telemetry_data['speed'] + 0.5) % 120
            telemetry_data['battery'] = max(0, telemetry_data['battery'] - 0.01)
            telemetry_data['heading'] = (telemetry_data['heading'] + 1) % 360
            telemetry_data['satellites'] = 12
            
        except socket.timeout:
            pass
        except Exception as e:
            print(f"UDP error: {str(e)}")
        
        # ExpressLRS telemetry
        if elrs is None:
            ports = get_serial_ports()
            for port in ports:
                try:
                    elrs = serial.Serial(port, 115200, timeout=1)
                    print(f"📶 Connected to ExpressLRS at {port}")
                    break
                except:
                    continue
        
        if elrs:
            try:
                if elrs.in_waiting:
                    packet = elrs.read(elrs.in_waiting)
                    # Process CRSF protocol
                    if len(packet) > 0 and packet[0] == 0x28:  # GPS packet
                        try:
                            lat = int.from_bytes(packet[1:5], 'big', signed=True)
                            lon = int.from_bytes(packet[5:9], 'big', signed=True)
                            telemetry_data['gps'] = (lat/1e7, lon/1e7)
                        except:
                            pass
            except Exception as e:
                print(f"ELRS error: {str(e)}")
                elrs = None
        sleep(0.1)

if __name__ == "__main__":
    # Start telemetry thread
    telemetry_thread = threading.Thread(target=handle_telemetry, daemon=True)
    telemetry_thread.start()
    
    # Start Taranis handler thread
    taranis_thread = threading.Thread(target=handle_taranis, daemon=True)
    taranis_thread.start()
    
    # Start Flask
    app.run(host='0.0.0.0', port=5000, threaded=True)