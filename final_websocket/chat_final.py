# draft1.py (REVISED WITH STABLE RECONNECT + STRICT CEEO LOGIC)
# Unified code for ESP32 controller and receiver using CEEO_Channel WebSocket format

import network
import socket
import json
import time
import ubinascii
import ussl
from machine import Pin, SoftI2C, ADC
import urandom
import icons
import _thread
import struct
import servo
import gc

SSID = "tufts_eecs"
PASSWORD = ""
WS_HOST = "chrisrogers.pyscriptapps.com"
WS_PORT = 443
WS_PATH = "/talking-on-a-channel/api/channels/hackathon"

class ESP32Device:
    def __init__(self, device_name="controller", listen_topic="/receiver/status"):
        self.device_name = device_name
        self.listen_topic = listen_topic
        self.send_topic = f"/{device_name}/status"
        self.ws = None
        self.connected = False
        self.display = None
        self.running = True

        self.servo = None
        self.servo_angle = 90
        self.knob = None
        self.knob_available = False
        self.last_potentiometer_angle = 90
        self.knob_dead_zone = 5
        self.knob_sample_size = 5
        self.receive_buffer = b""
        self.max_buffer_size = 2048

        self.setup_display()
        self.setup_hardware()
        self.setup_wifi()

    def setup_display(self):
        try:
            i2c = SoftI2C(scl=Pin(7), sda=Pin(6))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))
            self.display.fill(0)
            self.display.text("ESP32", 45, 10)
            self.display.text(self.device_name[:12], 25, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()
        except Exception as e:
            print(f"Display setup failed: {e}")
            self.display = None

    def update_display(self, line1="ESP32", line2="", line3="", line4=""):
        if self.display:
            try:
                self.display.fill(0)
                self.display.text(line1[:16], 0, 10)
                self.display.text(line2[:16], 0, 25)
                if line3:
                    self.display.text(line3[:16], 0, 40)
                if line4:
                    self.display.text(line4[:16], 0, 55)
                self.display.show()
            except Exception as e:
                print(f"Display update error: {e}")

    def setup_hardware(self):
        if self.device_name == "receiver":
            try:
                self.servo = servo.Servo(Pin(2))
                self.servo.write_angle(90)
                print("Servo initialized")
            except Exception as e:
                print(f"Servo setup failed: {e}")
                self.servo = None
        elif self.device_name == "controller":
            try:
                self.knob = ADC(Pin(3))
                self.knob.atten(ADC.ATTN_11DB)
                self.knob_available = True
                print("Potentiometer initialized")
            except Exception as e:
                print(f"Potentiometer setup failed: {e}")
                self.knob_available = False

    def setup_wifi(self):
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        if not wlan.isconnected():
            wlan.connect(SSID, PASSWORD)
            timeout = 0
            while not wlan.isconnected() and timeout < 30:
                print(".", end="")
                time.sleep(1)
                timeout += 1
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"WiFi connected: {ip}")
            self.update_display("ESP32", self.device_name, "WiFi OK", ip)
        else:
            print("WiFi connection failed")
            self.update_display("ESP32", self.device_name, "WiFi FAIL", "Check creds")

    def generate_websocket_key(self):
        key_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
        return ubinascii.b2a_base64(key_bytes).decode().strip()

    def connect_websocket(self):
        try:
            gc.collect()
            addr_info = socket.getaddrinfo(WS_HOST, WS_PORT)
            addr = addr_info[0][-1]
            raw_sock = socket.socket()
            raw_sock.settimeout(10)
            raw_sock.connect(addr)
            self.ws = ussl.wrap_socket(raw_sock, server_hostname=WS_HOST)

            ws_key = self.generate_websocket_key()
            handshake = (
                "GET {} HTTP/1.1\r\n"
                "Host: {}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: {}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Origin: https://esp32-device\r\n"
                "\r\n"
            ).format(WS_PATH, WS_HOST, ws_key)

            self.ws.write(handshake.encode())
            response = b""
            while b"\r\n\r\n" not in response:
                chunk = self.ws.read(1024)
                if not chunk:
                    break
                response += chunk

            if b"101 Switching Protocols" in response:
                self.ws.setblocking(False)
                self.connected = True
                print("WebSocket connected successfully")
                self.update_display("ESP32", self.device_name, "WS Connected", "Listening...")
                return True
            else:
                print("WebSocket handshake failed")
                self.update_display("ESP32", self.device_name, "WS Failed", "Handshake")
                return False

        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.update_display("ESP32", self.device_name, "WS Error", str(e)[:16])
            return False

    def listen_loop(self):
        while self.running:
            if not self.connected:
                print("[INFO] Attempting reconnect...")
                if self.connect_websocket():
                    try:
                        _thread.start_new_thread(self.sender_loop, ())
                    except:
                        pass
                else:
                    time.sleep(5)
                    continue

            try:
                data = self.ws.read(128)
                if data:
                    self.receive_buffer += data
                    buffer_str = self.receive_buffer.decode("utf-8", errors="ignore")
                    start = buffer_str.find("{")
                    end = buffer_str.rfind("}") + 1
                    if start != -1 and end > start:
                        msg = buffer_str[start:end]
                        self.receive_buffer = b""
                        print("[DEBUG] Message parsed:", msg)
                        self.handle_message(msg)
                time.sleep(0.05)
            except Exception as e:
                print(f"[ERROR] Listen error: {e}")
                self.connected = False
                time.sleep(1)

    def sender_loop(self):
        count = 0
        while self.running:
            try:
                if self.connected:
                    if self.device_name == "controller":
                        angle = self.read_potentiometer()
                        if abs(angle - self.last_potentiometer_angle) > self.knob_dead_zone:
                            data = {
                                "device": "controller",
                                "potentiometer_angle": angle,
                                "count": count
                            }
                            if self.send_ceeo_message(self.send_topic, data):
                                self.last_potentiometer_angle = angle
                                count += 1
                    elif self.device_name == "receiver":
                        data = {
                            "device": "receiver",
                            "servo_angle": self.servo_angle,
                            "count": count
                        }
                        if self.send_ceeo_message(self.send_topic, data):
                            count += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"Sender error: {e}")
                time.sleep(1)

    def run(self):
        print(f"Starting ESP32 {self.device_name}")
        while self.running:
            if not self.connected:
                if not self.connect_websocket():
                    time.sleep(5)
                    continue
                _thread.start_new_thread(self.sender_loop, ())
            self.listen_loop()

DEVICE_NAME = "controller"  # or "receiver"
LISTEN_TOPIC = "/receiver/status" if DEVICE_NAME == "controller" else "/controller/status"

controller = ESP32Device(DEVICE_NAME, LISTEN_TOPIC)
controller.run()

