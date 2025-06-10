import network
import socket
import json
import time
import ubinascii
import ussl
from machine import Pin, SoftI2C
import urandom
import icons

# WiFi Configuration
SSID = "tufts_eecs"
PASSWORD = ""

# WebSocket Configuration
WS_HOST = "chrisrogers.pyscriptapps.com"
WS_PORT = 443
WS_PATH = "/talking-on-a-channel/api/channels/hackathon"

class ESP32Controller:
    def __init__(self):
        self.ws = None
        self.connected = False
        self.display = None
        self.setup_display()
        self.setup_wifi()
        
    def setup_display(self):
        """Setup SSD1306 display if available"""
        try:
            # Try to import and setup display
            import ssd1306
            i2c = SoftI2C(scl=Pin(7), sda=Pin(6))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))
            self.display.fill(0)
            self.display.text("ESP32", 45, 10)
            self.display.text("Controller", 25, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()
            print("Display initialized")
        except Exception as e:
            print(f"Display setup failed: {e}")
            self.display = None
    
    def update_display(self, line1="ESP32", line2="Controller", line3="", line4=""):
        """Update display with status"""
        if self.display:
            try:
                self.display.fill(0)
                self.display.text(line1, 0, 0)
                self.display.text(line2, 0, 15)
                if line3:
                    self.display.text(line3, 0, 30)
                if line4:
                    self.display.text(line4, 0, 45)
                self.display.show()
            except Exception as e:
                print(f"Display update error: {e}")
        
    def setup_wifi(self):
        print("Connecting to WiFi...")
        self.update_display("ESP32", "Controller", "WiFi...", "Connecting")
        
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
            print(f"\nWiFi connected! IP: {ip}")
            self.update_display("ESP32", "Controller", "WiFi OK", ip)
            time.sleep(2)
            return True
        else:
            print("\nWiFi connection failed!")
            self.update_display("ESP32", "Controller", "WiFi FAIL", "Check creds")
            return False
    
    def generate_websocket_key(self):
        key_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
        return ubinascii.b2a_base64(key_bytes).decode().strip()
    
    def connect_websocket(self):
        try:
            print("Connecting to WebSocket...")
            self.update_display("ESP32", "Controller", "WebSocket", "Connecting...")
            
            addr_info = socket.getaddrinfo(WS_HOST, WS_PORT)
            addr = addr_info[0][-1]
            
            # Create SSL socket
            raw_sock = socket.socket()
            raw_sock.connect(addr)
            self.ws = ussl.wrap_socket(raw_sock, server_hostname=WS_HOST)
            
            # WebSocket handshake
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
            
            # Read handshake response
            response = b""
            while b'\r\n\r\n' not in response:
                chunk = self.ws.read(1024)
                if not chunk:
                    break
                response += chunk
            
            if b"101 Switching Protocols" in response:
                print("WebSocket connected successfully!")
                self.update_display("ESP32", "Controller", "Connected", "Sending data")
                self.connected = True
                return True
            else:
                print("WebSocket handshake failed")
                self.update_display("ESP32", "Controller", "WS Failed", "Handshake")
                return False
                
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.update_display("ESP32", "Controller", "WS Error", str(e)[:16])
            return False
    
    def send_message(self, topic, value):
        if not self.connected:
            return False
            
        try:
            # Create message in CEEO_Channel format
            message = {
                "topic": topic,
                "value": value
            }
            
            json_data = json.dumps(message)
            payload = json_data.encode('utf-8')
            length = len(payload)
            
            # Create WebSocket frame (text frame with masking)
            frame = bytearray()
            frame.append(0x81)  # FIN=1, opcode=1 (text)
            
            # Generate random mask key
            mask_key = bytearray([urandom.getrandbits(8) for _ in range(4)])
            
            # Add length and mask bit
            if length <= 125:
                frame.append(0x80 | length)  # MASK=1, length
            elif length < 65536:
                frame.append(0x80 | 126)  # MASK=1, extended length
                frame.extend(length.to_bytes(2, 'big'))
            else:
                frame.append(0x80 | 127)  # MASK=1, extended length
                frame.extend(length.to_bytes(8, 'big'))
            
            # Add mask key
            frame.extend(mask_key)
            
            # Mask and add payload
            for i in range(length):
                frame.append(payload[i] ^ mask_key[i % 4])
            
            self.ws.write(frame)
            print(f"Sent: {topic} = {value}")
            return True
            
        except Exception as e:
            print(f"Send error: {e}")
            self.connected = False
            return False
    
    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
        self.connected = False
    
    def run(self):
        print("Starting ESP32 Controller...")
        send_count = 0
        
        while True:
            try:
                # Connect if not connected
                if not self.connected:
                    self.update_display("ESP32", "Controller", "Disconnected", "Reconnecting")
                    if not self.connect_websocket():
                        print("Retrying connection in 5 seconds...")
                        time.sleep(5)
                        continue
                
                # Send controller data every 2 seconds
                timestamp = time.ticks_ms()
                controller_data = {
                    "device": "controller",
                    "timestamp": timestamp,
                    "status": "active",
                    "count": send_count
                }
                
                success = self.send_message("/controller/status", controller_data)
                
                if success:
                    send_count += 1
                    self.update_display("ESP32", "Controller", f"Sent: {send_count}", "Active")
                else:
                    print("Send failed, reconnecting...")
                    self.update_display("ESP32", "Controller", "Send Failed", "Reconnecting")
                    self.connected = False
                    self.close()
                
                time.sleep(2)
                
            except KeyboardInterrupt:
                print("Stopping controller...")
                self.update_display("ESP32", "Controller", "Stopped", "")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.update_display("ESP32", "Controller", "Error", str(e)[:16])
                self.connected = False
                self.close()
                time.sleep(5)
        
        self.close()

# Run the controller
if __name__ == "__main__":
    controller = ESP32Controller()
    controller.run()
