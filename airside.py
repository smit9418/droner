#!/usr/bin/env python3
import serial
import socket
import bluetooth
import threading
from time import sleep

# Configuration
SERIAL_PORT = "/dev/ttyAMA0"
BAUD_RATE = 115200
WIFI_IP = "192.168.1.100"  # Groundstation IP
WIFI_PORT = 14550
BLUETOOTH_ADDR = "00:11:22:33:44:55"  # Groundstation BT
ELRS_SERIAL = "/dev/ttyUSB0"  # If ExpressLRS moved to RPi

def handle_wifi(data):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(data, (WIFI_IP, WIFI_PORT))

def handle_bluetooth(data):
    sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    try:
        sock.connect((BLUETOOTH_ADDR, 1))
        sock.send(data)
    except: pass
    finally: sock.close()

def handle_elrs(data):
    with serial.Serial(ELRS_SERIAL, 115200, timeout=1) as ser:
        ser.write(data)

if __name__ == "__main__":
    fc_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    
    while True:
        data = fc_serial.readline()
        if data:
            # Forward data through all links
            threading.Thread(target=handle_wifi, args=(data,)).start()
            threading.Thread(target=handle_bluetooth, args=(data,)).start()
            threading.Thread(target=handle_elrs, args=(data,)).start()