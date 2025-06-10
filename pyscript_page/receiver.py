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

class ESP32Receiver:
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
            self.display.text("Receiver", 30, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()
            print("Display initialized")
        except Exception as e:
            print(f"Display setup failed: {e}")
            self.display = None
    
    def update_display(self, line1="ESP32", line2="Receiver", line3="", line4=""):
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
        self.update_display("ESP32", "Receiver", "WiFi...", "Connecting")
        
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
            self.update_display("ESP32", "Receiver", "WiFi OK", ip)
            time.sleep(2)
            return True
        else:
            print("\nWiFi connection failed!")
            self.update_display("ESP32", "Receiver", "WiFi FAIL", "Check creds")
            return False
    
    def generate_websocket_key(self):
        key_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
        return ubinascii.b2a_base64(key_bytes).decode().strip()
    
    def connect_websocket(self):
        try:
            print("Connecting to WebSocket...")
            self.update_display("ESP32", "Receiver", "WebSocket", "Connecting...")
            
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
                self.update_display("ESP32", "Receiver", "Connected", "Listening")
                self.connected = True
                return True
            else:
                print("WebSocket handshake failed")
                self.update_display("ESP32", "Receiver", "WS Failed", "Handshake")
                return False
                
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.update_display("ESP32", "Receiver", "WS Error", str(e)[:16])
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
    
    def parse_websocket_frame(self, frame_data):
        """Parse incoming WebSocket frames"""
        messages = []
        i = 0
        
        while i < len(frame_data):
            if i + 2 > len(frame_data):
                break
                
            b1 = frame_data[i]
            fin = (b1 & 0x80) >> 7
            opcode = b1 & 0x0F
            i += 1
            
            b2 = frame_data[i]
            mask = (b2 & 0x80) >> 7
            payload_len = b2 & 0x7F
            i += 1
            
            # Handle extended payload length
            if payload_len == 126:
                if i + 2 > len(frame_data):
                    break
                payload_len = int.from_bytes(frame_data[i:i+2], 'big')
                i += 2
            elif payload_len == 127:
                if i + 8 > len(frame_data):
                    break
                payload_len = int.from_bytes(frame_data[i:i+8], 'big')
                i += 8
            
            # Handle masking key
            if mask:
                if i + 4 > len(frame_data):
                    break
                mask_key = frame_data[i:i+4]
                i += 4
            
            # Check payload availability
            if i + payload_len > len(frame_data):
                break
                
            # Extract payload
            payload = bytearray(frame_data[i:i+payload_len])
            i += payload_len
            
            if mask:
                for j in range(payload_len):
                    payload[j] ^= mask_key[j % 4]
            
            # Handle different frame types
            if opcode == 0x1:  # Text frame
                try:
                    msg = json.loads(payload.decode('utf-8'))
                    messages.append(msg)
                except:
                    pass
            elif opcode == 0x9:  # Ping frame
                self.send_pong(payload)
        
        return messages
    
    def send_pong(self, payload=b''):
        """Send pong response to ping"""
        try:
            frame = bytearray()
            frame.append(0x8A)  # Pong frame
            frame.append(len(payload))
            frame.extend(payload)
            self.ws.write(frame)
        except:
            pass
    
    def listen_for_messages(self):
        """Listen for incoming WebSocket messages"""
        if not self.connected:
            return []
            
        try:
            # Try to read data (non-blocking for SSL sockets)
            data = self.ws.read(1024)
            if data:
                return self.parse_websocket_frame(data)
        except OSError as e:
            # Expected when no data is available
            if e.args[0] in (-110, 11, 9):  # ETIMEDOUT, EAGAIN, EBADF
                pass
            else:
                print(f"Listen error: {e}")
                self.connected = False
        except Exception as e:
            print(f"Listen error: {e}")
            self.connected = False
            
        return []
    
    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
        self.connected = False
    
    def run(self):
        print("Starting ESP32 Receiver...")
        last_send = 0
        receive_count = 0
        
        while True:
            try:
                # Connect if not connected
                if not self.connected:
                    self.update_display("ESP32", "Receiver", "Disconnected", "Reconnecting")
                    if not self.connect_websocket():
                        print("Retrying connection in 5 seconds...")
                        time.sleep(5)
                        continue
                
                # Listen for incoming messages
                messages = self.listen_for_messages()
                for msg in messages:
                    if msg.get('type') == 'data':
                        payload = msg.get('payload', {})
                        topic = payload.get('topic', '')
                        value = payload.get('value', {})
                        print(f"Received: {topic} = {value}")
                        receive_count += 1
                        self.update_display("ESP32", "Receiver", f"Recv: {receive_count}", "Active")
                    elif msg.get('type') == 'welcome':
                        print("Connected to channel successfully!")
                        self.update_display("ESP32", "Receiver", "Connected", "Ready")
                
                # Send receiver status every 3 seconds
                current_time = time.ticks_ms()
                if time.ticks_diff(current_time, last_send) > 3000:
                    receiver_data = {
                        "device": "receiver",
                        "timestamp": current_time,
                        "status": "listening",
                        "received": receive_count
                    }
                    
                    success = self.send_message("/receiver/status", receiver_data)
                    if success:
                        last_send = current_time
                    else:
                        print("Send failed, reconnecting...")
                        self.update_display("ESP32", "Receiver", "Send Failed", "Reconnecting")
                        self.connected = False
                        self.close()
                
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                print("Stopping receiver...")
                self.update_display("ESP32", "Receiver", "Stopped", "")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.update_display("ESP32", "Receiver", "Error", str(e)[:16])
                self.connected = False
                self.close()
                time.sleep(5)
        
        self.close()

# Run the receiver
if __name__ == "__main__":
    receiver = ESP32Receiver()
    receiver.run()
