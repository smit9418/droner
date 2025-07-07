#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from flask_socketio import SocketIO
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import threading
import time
import json
import os
import cv2
import numpy as np

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')

# Initialize SocketIO
socketio = SocketIO(app, async_mode='threading')

# Login Manager Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User Management
users = {
    'admin': {
        'password': generate_password_hash(os.getenv('ADMIN_PASSWORD', 'adminpass')),
        'role': 'admin'
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

# Video Feed Generation
def generate_frames():
    camera = cv2.VideoCapture(0)  # Use 0 for default camera
    while True:
        success, frame = camera.read()
        if not success:
            # Generate test pattern if camera fails
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "DRONE CAMERA FEED", (100, 240), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# Device Manager
class DeviceManager:
    def __init__(self):
        self.devices = {}
        self.telemetry = {}
    
    def add_device(self, device_info):
        device_id = device_info['mac']
        self.devices[device_id] = {
            **device_info,
            'last_seen': time.time(),
            'signal_strength': 0,
            'status': 'connected'
        }
        self.update_clients()
    
    def update_telemetry(self, device_id, data):
        self.telemetry[device_id] = data
        self.devices[device_id]['last_seen'] = time.time()
        self.update_clients()
    
    def update_signal(self, device_id, strength):
        if device_id in self.devices:
            self.devices[device_id]['signal_strength'] = strength
            self.update_clients()
    
    def update_clients(self):
        socketio.emit('device_update', {
            'devices': list(self.devices.values()),
            'telemetry': self.telemetry
        })

device_manager = DeviceManager()

# Routes
@app.route('/')
@login_required
def index():
    return render_template('index.html', user_role=users[current_user.id]['role'])

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
        
        return 'Invalid credentials', 401
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/video_feed')
@login_required
def video_feed():
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/device/settings', methods=['POST'])
@login_required
def device_settings():
    data = request.json
    device_id = data.get('device_id')
    settings = data.get('settings')
    
    if device_id in device_manager.devices:
        # Send settings to device (implementation specific)
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Device not found'}), 404

# SocketIO Events
@socketio.on('connect')
def handle_connect():
    emit('device_update', {
        'devices': list(device_manager.devices.values()),
        'telemetry': device_manager.telemetry
    })

@socketio.on('set_layout')
def handle_set_layout(preset):
    emit('layout_update', {'preset': preset}, broadcast=True)

# Background Threads
def telemetry_thread():
    while True:
        # Simulate telemetry updates
        for device_id in device_manager.devices:
            device_manager.update_telemetry(device_id, {
                'altitude': round(time.time() % 100, 1),
                'speed': round(time.time() % 50, 1),
                'battery': 100 - (time.time() % 100),
                'signal': device_manager.devices[device_id]['signal_strength']
            })
        time.sleep(0.5)

def simulate_devices():
    # Add some test devices
    device_manager.add_device({
        'id': 'drone1',
        'name': 'Primary Drone',
        'mac': '00:11:22:33:44:55',
        'ip': '192.168.1.100',
        'type': 'airside'
    })
    
    # Simulate signal strength changes
    while True:
        for device_id in device_manager.devices:
            device_manager.update_signal(device_id, (time.time() % 30) + 70)
        time.sleep(2)

if __name__ == "__main__":
    # Start background threads
    threading.Thread(target=telemetry_thread, daemon=True).start()
    threading.Thread(target=simulate_devices, daemon=True).start()
    
    # Start Flask-SocketIO
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)