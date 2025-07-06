#!/usr/bin/env python3
# groundstation.py - Cross-platform ground station
import sys
import json
import socket
import serial
import threading
import numpy as np
from time import sleep
import cv2
import pygame
from flask import Flask, Response, render_template, request
from pymavlink import mavutil

# Platform-specific configurations
IS_WINDOWS = sys.platform == 'win32'
IS_RASPBERRY = 'linux' in sys.platform and 'raspberrypi' in sys.uname().release.lower()

# Initialize Flask
app = Flask(__name__)
telemetry_data = {"altitude": 0, "speed": 0, "battery": 0, "gps": (0, 0), "mode": "MANUAL"}
ui_preset = "dashboard"

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
    # Windows-specific camera setup
    if IS_WINDOWS:
        cap = cv2.VideoCapture(0)  # First USB camera
        if not cap.isOpened():
            cap = cv2.VideoCapture(1)  # Second USB camera
    else:  # Raspberry Pi
        cap = cv2.VideoCapture(0)  # USB capture device
        
    if not cap.isOpened():
        print("⚠️ Video capture not available!")
        while True:
            # Create a blank image with error message
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, "NO VIDEO SIGNAL", (100, 240), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            _, jpeg = cv2.imencode('.jpg', img)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
    
    while True:
        ret, frame = cap.read()
        if ret:
            # Add telemetry overlay
            cv2.putText(frame, f"ALT: {telemetry_data['altitude']}m", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"BAT: {telemetry_data['battery']}%", (10, 60), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
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
def set_preset():
    """Set UI preset"""
    global ui_preset
    data = request.json
    ui_preset = data.get('preset', 'dashboard')
    return "OK"

@app.route('/')
def index():
    """Web UI interface"""
    return render_template('index.html')

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
                    # Example: "CH1:1500,CH2:1200,..."
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
            # This is simplified - use pymavlink in real implementation
            if b'GPS' in data:
                # Extract GPS data
                pass
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
                    # Example: Update telemetry from ELRS
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

def draw_ui(screen):
    """Render PyGame UI"""
    global ui_preset
    
    screen.fill((0, 20, 40))  # Dark blue background
    
    # Draw UI based on preset
    if ui_preset == "dashboard":
        # Draw flight instruments
        font = pygame.font.SysFont('Arial', 24)
        alt_text = font.render(f"Altitude: {telemetry_data['altitude']}m", True, (0, 255, 0))
        speed_text = font.render(f"Speed: {telemetry_data['speed']}km/h", True, (0, 255, 0))
        bat_text = font.render(f"Battery: {telemetry_data['battery']}%", True, (0, 255, 0))
        
        screen.blit(alt_text, (50, 50))
        screen.blit(speed_text, (50, 90))
        screen.blit(bat_text, (50, 130))
        
        # Draw artificial horizon
        pygame.draw.rect(screen, (30, 30, 60), (300, 100, 200, 150), 2)
        
    elif ui_preset == "map":
        # Draw map background
        pygame.draw.rect(screen, (20, 50, 20), (0, 0, screen.get_width(), screen.get_height()))
        # Draw GPS position
        try:
            lat, lon = telemetry_data['gps']
            # Scale GPS coordinates to screen
            x = int(lat) % screen.get_width()
            y = int(lon) % screen.get_height()
            # Fixed syntax: properly closed circle function call
            pygame.draw.circle(screen, (255, 0, 0), (x, y), 10)
        except:
            pass
    
    # Draw preset buttons
    pygame.draw.rect(screen, (40, 40, 80), (10, 10, 120, 30))
    pygame.draw.rect(screen, (40, 40, 80), (140, 10, 120, 30))
    
    font = pygame.font.SysFont('Arial', 18)
    screen.blit(font.render("Dashboard", True, (255, 255, 255)), (20, 15))
    screen.blit(font.render("Map View", True, (255, 255, 255)), (150, 15))
    
    pygame.display.flip()

def run_pygame_ui():
    """Run PyGame UI (for Raspberry Pi touchscreen)"""
    global ui_preset
    
    if IS_WINDOWS:
        screen = pygame.display.set_mode((800, 600))
    else:
        # Raspberry Pi touchscreen setup
        pygame.init()
        screen = pygame.display.set_mode((800, 480), pygame.FULLSCREEN)
        pygame.mouse.set_visible(True)
    
    clock = pygame.time.Clock()
    running = True
    
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                x, y = event.pos
                # Check button clicks
                if 10 < x < 130 and 10 < y < 40:
                    ui_preset = "dashboard"
                elif 140 < x < 260 and 10 < y < 40:
                    ui_preset = "map"
                # Add more button regions as needed
        
        draw_ui(screen)
        clock.tick(30)
    
    pygame.quit()

if __name__ == "__main__":
    # Initialize pygame for potential UI
    pygame.init()
    
    # Start telemetry thread
    telemetry_thread = threading.Thread(target=handle_telemetry, daemon=True)
    telemetry_thread.start()
    
    # Start Taranis handler thread
    taranis_thread = threading.Thread(target=handle_taranis, daemon=True)
    taranis_thread.start()
    
    # Start Flask in background
    flask_thread = threading.Thread(target=app.run, 
                                  kwargs={'host': '0.0.0.0', 'port': 5000, 'threaded': True})
    flask_thread.daemon = True
    flask_thread.start()
    
    # Run PyGame UI on Raspberry Pi
    if IS_RASPBERRY:
        run_pygame_ui()
    else:
        print("✅ Ground station running")
        print(f"🌐 Web UI: http://localhost:5000")
        print("Press Ctrl+C to exit")
        try:
            while True: 
                sleep(1)
        except KeyboardInterrupt:
            pygame.quit()
            sys.exit(0)