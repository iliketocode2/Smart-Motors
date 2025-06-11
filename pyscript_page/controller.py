import network
import socket
import json
import time
import ubinascii
import ussl
from machine import Pin, SoftI2C
import urandom
import icons
import _thread
import struct

# WiFi Configuration
SSID = "tufts_eecs" 
PASSWORD = ""

# WebSocket Configuration
WS_HOST = "chrisrogers.pyscriptapps.com"
WS_PORT = 443
WS_PATH = "/talking-on-a-channel/api/channels/hackathon"

class ESP32Controller:
    def __init__(self, device_name="controller", listen_topic="/receiver/status"):
        self.device_name = device_name
        self.listen_topic = listen_topic
        self.send_topic = f"/{device_name}/status"
        self.ws = None
        self.connected = False
        self.display = None
        self.running = True
        self.last_received = {}
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
            raw_sock.settimeout(10)  # Set timeout for connection
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
    
    def parse_websocket_frame(self, data):
        """Parse incoming WebSocket frame"""
        if len(data) < 2:
            return None
            
        # Parse frame header
        byte1, byte2 = data[0], data[1]
        fin = (byte1 & 0x80) >> 7
        opcode = byte1 & 0x0f
        masked = (byte2 & 0x80) >> 7
        payload_length = byte2 & 0x7f
        
        offset = 2
        
        # Handle extended payload length
        if payload_length == 126:
            if len(data) < offset + 2:
                return None
            payload_length = struct.unpack('>H', data[offset:offset+2])[0]
            offset += 2
        elif payload_length == 127:
            if len(data) < offset + 8:
                return None
            payload_length = struct.unpack('>Q', data[offset:offset+8])[0]
            offset += 8
        
        # Handle masking key
        if masked:
            if len(data) < offset + 4:
                return None
            mask_key = data[offset:offset+4]
            offset += 4
        
        # Extract payload
        if len(data) < offset + payload_length:
            return None
            
        payload = data[offset:offset+payload_length]
        
        # Unmask payload if needed
        if masked:
            payload = bytearray(payload)
            for i in range(len(payload)):
                payload[i] ^= mask_key[i % 4]
            payload = bytes(payload)
        
        # Only handle text frames
        if opcode == 1 and fin == 1:
            return payload.decode('utf-8')
        
        return None
    
    def handle_message(self, message_str):
        """Handle incoming message"""
        try:
            # Parse the channel message format
            channel_message = json.loads(message_str)
            if 'payload' in channel_message:
                payload_dict = json.loads(channel_message['payload'])
                topic = payload_dict.get('topic', '')
                value = payload_dict.get('value', '')
                
                print(f"Received: {topic} = {value}")
                
                # Check if this is the topic we're listening for
                if topic == self.listen_topic:
                    self.last_received = value
                    print(f"Processing message from {topic}: {value}")
                    
                    # Update display with received data
                    if isinstance(value, dict) and 'count' in value:
                        self.update_display(
                            "ESP32", 
                            "Controller",
                            f"Sent: {send_count}",
                            f"Rcvd: {value.get('count', 0)}"
                        )
                    
                    # Add your custom message handling logic here
                    self.process_received_message(topic, value)
                    
        except Exception as e:
            print(f"Message handling error: {e}")
    
    def process_received_message(self, topic, value):
        """Override this method to add custom message processing"""
        # Example: if we receive a command, we could respond
        if isinstance(value, dict):
            if value.get('command') == 'ping':
                response_data = {
                    "device": self.device_name,
                    "response": "pong",
                    "timestamp": time.ticks_ms()
                }
                self.send_message(f"/{self.device_name}/response", response_data)
    
    def safe_decode(self, data):
        """Safely decode bytes to string, handling invalid UTF-8"""
        try:
            return data.decode('utf-8')
        except:
            # Fall back to latin-1 which can decode any byte sequence
            try:
                return data.decode('latin-1')
            except:
                # Last resort: decode with replacement character by character
                result = ""
                for byte in data:
                    if 32 <= byte <= 126:  # Printable ASCII
                        result += chr(byte)
                    else:
                        result += '?'
                return result
    
    def listen_for_messages(self):
        """Listen for incoming WebSocket messages - simplified version"""
        
        while self.running and self.connected:
            try:
                # Simple approach: try to read with a very short operation
                # Use select-like behavior by attempting read with minimal blocking
                data = self.ws.read(1)
                if data:
                    # If we got data, try to read more
                    more_data = b""
                    try:
                        # Try to read more, but don't block forever
                        while len(more_data) < 1024:  # Reasonable limit
                            chunk = self.ws.read(1)
                            if chunk:
                                more_data += chunk
                            else:
                                break
                    except:
                        pass
                    
                    full_data = data + more_data
                    
                    # Simple message extraction - look for JSON patterns
                    # FIXED: Use safe_decode instead of decode with errors parameter
                    data_str = self.safe_decode(full_data)
                    if '"topic"' in data_str and '"value"' in data_str:
                        # Try to extract JSON from the WebSocket frame
                        try:
                            # Find JSON content (simplified extraction)
                            start = data_str.find('{')
                            if start != -1:
                                end = data_str.rfind('}') + 1
                                if end > start:
                                    json_str = data_str[start:end]
                                    self.handle_message(json_str)
                        except Exception as e:
                            print(f"JSON parse error: {e}")
                
                # Small delay to prevent busy waiting  
                time.sleep(0.1)
                        
            except OSError as e:
                # Handle various socket errors
                error_msg = str(e)
                if "timeout" in error_msg.lower() or "would block" in error_msg.lower() or "EAGAIN" in error_msg:
                    # These are expected for non-blocking operations
                    time.sleep(0.1)
                    continue
                else:
                    print(f"Listen socket error: {e}")
                    self.connected = False
                    break
            except Exception as e:
                print(f"Listen error: {e}")
                time.sleep(0.1)  # Brief pause before retrying
    
    def sender_loop(self):
        """Main sending loop"""
        send_count = 0
        
        while self.running:
            try:
                if self.connected:
                    # Send controller data every 2 seconds
                    timestamp = time.ticks_ms()
                    controller_data = {
                        "device": self.device_name,
                        "timestamp": timestamp,
                        "status": "active",
                        "count": send_count,
                        "listening_to": self.listen_topic
                    }
                    
                    success = self.send_message(self.send_topic, controller_data)
                    
                    if success:
                        send_count += 1
                        print(f"Sent count: {send_count}")
                    else:
                        print("Send failed, will reconnect...")
                        self.connected = False
                
                time.sleep(2)
                
            except Exception as e:
                print(f"Sender loop error: {e}")
                self.connected = False
                time.sleep(1)
    
    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
        self.connected = False
        self.running = False
    
    def run(self):
        print(f"Starting ESP32 {self.device_name}...")
        print(f"Will send to: {self.send_topic}")
        print(f"Will listen to: {self.listen_topic}")
        
        while self.running:
            try:
                # Connect if not connected
                if not self.connected:
                    self.update_display("ESP32", "Controller", "Disconnected", "Reconnecting")
                    if not self.connect_websocket():
                        print("Retrying connection in 5 seconds...")
                        time.sleep(5)
                        continue
                
                # Start sender thread if threading is available
                try:
                    _thread.start_new_thread(self.sender_loop, ())
                    print("Sender thread started")
                    # Main loop handles receiving
                    self.listen_for_messages()
                except:
                    print("Threading not available, running single-threaded")
                    # Fall back to single-threaded operation
                    # Alternate between sending and listening
                    send_count = 0
                    last_send_time = 0
                    
                    while self.running and self.connected:
                        current_time = time.ticks_ms()
                        
                        # Send every 2 seconds
                        if time.ticks_diff(current_time, last_send_time) > 2000:
                            timestamp = time.ticks_ms()
                            controller_data = {
                                "device": self.device_name,
                                "timestamp": timestamp,
                                "status": "active",
                                "count": send_count,
                                "listening_to": self.listen_topic
                            }
                            
                            success = self.send_message(self.send_topic, controller_data)
                            
                            if success:
                                send_count += 1
                                self.update_display("ESP32", "Controller", f"Sent: {send_count}", "Active")
                                last_send_time = current_time
                            else:
                                print("Send failed, will reconnect...")
                                self.connected = False
                                break
                        
                        # Try to listen for a short time
                        try:
                            data = self.ws.read(1)
                            if data:
                                # Process received data (simplified)
                                print("Received data:", data)
                        except:
                            pass
                        
                        time.sleep(0.1)
                
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

# Configuration for different devices
# For the "controller" ESP32:
# controller = ESP32Controller("controller", "/receiver/status")

# For the "receiver" ESP32:
# controller = ESP32Controller("receiver", "/controller/status")

# Run the controller
if __name__ == "__main__":
    # Change these parameters based on which ESP32 this is running on
    DEVICE_NAME = "receiver"  # Change to "receiver" for the other ESP32
    LISTEN_TOPIC = "/controller/status"  # Change to "/controller/status" for the other ESP32
    
    controller = ESP32Controller(DEVICE_NAME, LISTEN_TOPIC)
    controller.run()

