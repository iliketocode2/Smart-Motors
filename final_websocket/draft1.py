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

# WiFi Configuration
SSID = "tufts_eecs"
PASSWORD = ""

# WebSocket Configuration
WS_HOST = "chrisrogers.pyscriptapps.com"
WS_PORT = 443
WS_PATH = "/talking-on-a-channel/api/channels/hackathon"

class ESP32ServoController:
    def __init__(self, device_name="controller", listen_topic="/receiver/status"):
        self.device_name = device_name
        self.listen_topic = listen_topic
        self.send_topic = f"/{device_name}/status"
        self.ws = None
        self.connected = False
        self.display = None
        self.running = True
        self.last_received = {}
        
        # Hardware setup based on your control_center.py
        self.setup_hardware()
        self.setup_wifi()
        
        # Control variables
        self.servo_angle = 90
        self.last_servo_angle = 90
        self.potentiometer_angle = 90
        self.last_potentiometer_angle = 90
        
        # Potentiometer filtering - reduced for better memory management
        self.knob_readings = []
        self.knob_sample_size = 5  # Reduced significantly to save memory
        self.knob_last_stable_angle = 90
        self.knob_dead_zone = 5  # Increased to reduce network traffic
        
        # Add receive buffer management
        self.receive_buffer = b""
        self.max_buffer_size = 2048  # Limit buffer size
        
    def setup_hardware(self):
        """Setup hardware based on your control_center.py"""
        try:
            # Setup display
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
        
        # Setup servo (for receiver ESP32)
        if self.device_name == "receiver":
            try:
                self.servo = servo.Servo(Pin(2))  # Same pin as your control_center.py
                self.servo.write_angle(90)  # Center position
                print("Servo initialized on Pin 2")
            except Exception as e:
                print(f"Servo setup failed: {e}")
                self.servo = None
        else:
            self.servo = None
        
        # Setup potentiometer (for controller ESP32)
        if self.device_name == "controller":
            try:
                self.knob = ADC(Pin(3))  # Pin 3 as per your control_center.py
                self.knob.atten(ADC.ATTN_11DB)  # Full range 0-3.3V
                # Test read
                test_read = self.knob.read()
                if 0 <= test_read <= 4095:
                    self.knob_available = True
                    print(f"Potentiometer initialized on Pin 3")
                else:
                    self.knob_available = False
                    print(f"Potentiometer reading out of range: {test_read}")
            except Exception as e:
                print(f"Potentiometer setup failed: {e}")
                self.knob_available = False
                self.knob = None
        else:
            self.knob_available = False
            self.knob = None
    
    def update_display(self, line1="ESP32", line2="Controller", line3="", line4=""):
        """Update display with status - Fixed positioning"""
        if self.display:
            try:
                self.display.fill(0)
                # Use consistent Y positioning: 10, 25, 40, 55 (within 64px height)
                # Center text horizontally where possible
                self.display.text(line1[:16], 0, 10)  # Limit to 16 chars max
                self.display.text(line2[:16], 0, 25)
                if line3:
                    self.display.text(line3[:16], 0, 40)
                if line4:
                    self.display.text(line4[:16], 0, 55)
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
            # Truncate IP for display
            ip_short = ip[:15] if len(ip) > 15 else ip
            self.update_display("ESP32", "Controller", "WiFi OK", ip_short)
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
            
            # Limit message size to prevent memory issues
            if length > 1024:
                print("Message too large, skipping")
                return False
            
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
            
            # Force garbage collection after sending
            gc.collect()
            return True
            
        except Exception as e:
            print(f"Send error: {e}")
            self.connected = False
            return False
    
    def parse_websocket_frame(self, data):
        """Parse incoming WebSocket frame with better error handling"""
        try:
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
            
            # Limit payload size to prevent memory issues
            if payload_length > 2048:
                print(f"Payload too large: {payload_length}")
                return None
            
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
            
        except Exception as e:
            print(f"Frame parsing error: {e}")
            return None
    
    def handle_message(self, message_str):
        """Handle incoming CEEO channel message"""
        try:
            print(f"Received: {message_str}")
            
            # Parse CEEO channel message
            channel_msg = json.loads(message_str)
            
            if channel_msg.get('type') == 'welcome':
                print("Channel connection confirmed")
                return
            
            if channel_msg.get('type') == 'data' and 'payload' in channel_msg:
                payload = json.loads(channel_msg['payload'])
                topic = payload.get('topic', '')
                value = payload.get('value', {})
                
                print(f"Topic: {topic}, Value: {value}")
                
                # Check if this message is for us
                if topic == self.listen_topic:
                    self.process_message(value)
                    
        except Exception as e:
            print(f"Message handling error: {e}")
    
    def process_message(self, data):
        """Process received data based on device type"""
        if not isinstance(data, dict):
            return
        
        if self.device_name == "receiver":
            # Receiver: move servo based on controller's potentiometer
            if 'potentiometer_angle' in data:
                angle = data['potentiometer_angle']
                if isinstance(angle, (int, float)):
                    angle = max(0, min(180, int(angle)))
                    print(f"Moving servo to {angle}°")
                    if self.move_servo(angle):
                        self.servo_angle = angle
        
        elif self.device_name == "controller":
            # Controller: display receiver's servo position
            if 'servo_angle' in data:
                angle = data['servo_angle']
                print(f"Receiver servo at {angle}°")
    
    def read_potentiometer(self):
        """Simple potentiometer reading method"""
        if not self.knob_available:
            return 90
        
        try:
            raw_value = self.knob.read()
            # Map from ADC range (0-4095) to servo angle (0-180)
            angle = int((180.0 / 4095.0) * raw_value)
            angle = max(0, min(180, angle))
            return angle
        except Exception as e:
            print(f"Potentiometer read error: {e}")
            return 90
    
    def read_potentiometer_smooth(self):
        """Read potentiometer with reduced sampling for better performance"""
        if not self.knob_available:
            return 90
        
        try:
            # Reduced sampling for better memory management
            readings = []
            for i in range(self.knob_sample_size):
                raw_value = self.knob.read()
                readings.append(raw_value)
                time.sleep(0.001)  # Small delay between readings
            
            # Simple average instead of complex filtering
            average_raw = sum(readings) / len(readings)
            
            # Map from ADC range (0-4095) to servo angle (0-180)
            angle = int((180.0 / 4095.0) * average_raw)
            angle = max(0, min(180, angle))
            
            # Apply dead zone to prevent jitter
            if abs(angle - self.knob_last_stable_angle) > self.knob_dead_zone:
                self.knob_last_stable_angle = angle
            
            return self.knob_last_stable_angle
            
        except Exception as e:
            print(f"Potentiometer read error: {e}")
            return self.knob_last_stable_angle
    
    def move_servo(self, angle):
        """Move servo to specified angle with error handling"""
        if self.servo:
            try:
                print(f"Attempting to move servo to {angle}°")
                self.servo.write_angle(angle)
                time.sleep(0.1)  # Give servo time to move
                return True
            except Exception as e:
                print(f"Servo move error: {e}")
                return False
        else:
            print("No servo available")
            return False
    
    def listen_for_messages(self):
        """Listen for incoming messages - FIXED: Use read() instead of recv()"""
        while self.running and self.connected:
            try:
                # FIXED: Use read() instead of recv() for SSL sockets
                data = self.ws.read(1024)
                if data:
                    # Handle the data as bytes
                    if isinstance(data, bytes):
                        self.receive_buffer += data
                    else:
                        # If it's already a string, encode it
                        self.receive_buffer += data.encode('utf-8', errors='ignore')
                    
                    # Look for complete JSON messages
                    while b'{' in self.receive_buffer and b'}' in self.receive_buffer:
                        try:
                            # Convert to string for processing
                            buffer_str = self.receive_buffer.decode('utf-8', errors='ignore')
                            start = buffer_str.find('{')
                            if start == -1:
                                break
                            
                            # Find matching closing brace
                            brace_count = 0
                            end = -1
                            for i in range(start, len(buffer_str)):
                                if buffer_str[i] == '{':
                                    brace_count += 1
                                elif buffer_str[i] == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        end = i + 1
                                        break
                            
                            if end != -1:
                                message = buffer_str[start:end]
                                # Remove processed part from buffer
                                remaining = buffer_str[end:].encode('utf-8')
                                self.receive_buffer = remaining
                                self.handle_message(message)
                                break
                            else:
                                break
                        except Exception as e:
                            print(f"Message parsing error: {e}")
                            # Clear buffer on parse error
                            self.receive_buffer = b""
                            break
                
                    # Limit buffer size to prevent memory issues
                    if len(self.receive_buffer) > self.max_buffer_size:
                        self.receive_buffer = self.receive_buffer[-1024:]  # Keep last 1KB
                
                time.sleep(0.05)
                
            except OSError:
                # Timeout or no data - continue
                time.sleep(0.1)
            except Exception as e:
                print(f"Listen error: {e}")
                self.connected = False
                break
    
    def sender_loop(self):
        """Main sending loop"""
        send_count = 0
        last_send_time = 0
        
        while self.running:
            try:
                if not self.connected:
                    time.sleep(1)
                    continue
                
                current_time = time.ticks_ms()
                
                # Send data every 500ms
                if time.ticks_diff(current_time, last_send_time) > 500:
                    
                    if self.device_name == "controller":
                        # Send potentiometer reading - FIXED: Use correct method name
                        angle = self.read_potentiometer()
                        
                        # Only send if angle changed significantly
                        if abs(angle - self.last_potentiometer_angle) > 2:
                            data = {
                                "device": "controller",
                                "potentiometer_angle": angle,
                                "count": send_count
                            }
                            
                            if self.send_message(self.send_topic, data):
                                self.last_potentiometer_angle = angle
                                send_count += 1
                    
                    elif self.device_name == "receiver":
                        # Send servo status
                        data = {
                            "device": "receiver", 
                            "servo_angle": self.servo_angle,
                            "count": send_count
                        }
                        
                        if self.send_message(self.send_topic, data):
                            send_count += 1
                    
                    last_send_time = current_time
                    gc.collect()
                
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Sender error: {e}")
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
        
        # Return servo to center if this is receiver
        if self.device_name == "receiver" and self.servo:
            self.move_servo(90)
    
    def run(self):
        print(f"Starting ESP32 {self.device_name}...")
        print(f"Will send to: {self.send_topic}")
        print(f"Will listen to: {self.listen_topic}")
        
        if self.device_name == "controller":
            if self.knob_available:
                print("Controller mode: Sending potentiometer readings")
            else:
                print("Warning: Potentiometer not available - check Pin 3")
        elif self.device_name == "receiver":
            if self.servo:
                print("Receiver mode: Controlling servo from remote potentiometer")
            else:
                print("Warning: Servo not available - check Pin 2")
        
        while self.running:
            try:
                if not self.connected:
                    self.update_display("ESP32", self.device_name[:12], "Disconnected", "Reconnecting")
                    if not self.connect_websocket():
                        print("Retrying connection in 5 seconds...")
                        time.sleep(5)
                        continue
                
                # Start sender thread
                try:
                    _thread.start_new_thread(self.sender_loop, ())
                    print("Sender thread started")
                    # Main loop handles receiving
                    self.listen_for_messages()
                except:
                    print("Threading not available, running single-threaded")
                    # Single-threaded fallback with reduced frequency
                    send_count = 0
                    last_send_time = 0
                    
                    while self.running and self.connected:
                        current_time = time.ticks_ms()
                        
                        # Send every 500ms instead of 200ms
                        if time.ticks_diff(current_time, last_send_time) > 500:
                            if self.device_name == "controller":
                                new_pot_angle = self.read_potentiometer_smooth()
                                if abs(new_pot_angle - self.last_potentiometer_angle) > self.knob_dead_zone:
                                    controller_data = {
                                        "device": "controller",
                                        "potentiometer_angle": new_pot_angle,
                                        "count": send_count
                                    }
                                    
                                    success = self.send_message(self.send_topic, controller_data)
                                    if success:
                                        self.last_potentiometer_angle = new_pot_angle
                                        send_count += 1
                                        self.update_display(
                                            "CONTROLLER",
                                            "Potentiometer",
                                            f"Angle: {new_pot_angle}",
                                            f"Sent: {send_count}"
                                        )
                                    else:
                                        self.connected = False
                                        break
                                        
                            elif self.device_name == "receiver":
                                receiver_data = {
                                    "device": "receiver",
                                    "servo_angle": self.servo_angle,
                                    "count": send_count
                                }
                                
                                success = self.send_message(self.send_topic, receiver_data)
                                if success:
                                    send_count += 1
                                    self.update_display(
                                        "RECEIVER",
                                        "Servo Motor",
                                        f"Angle: {self.servo_angle}",
                                        f"Updates: {send_count}"
                                    )
                                else:
                                    self.connected = False
                                    break
                            
                            last_send_time = current_time
                            gc.collect()  # Force garbage collection
                        
                        # Try to listen with smaller buffer - FIXED: Use read() instead of recv()
                        try:
                            data = self.ws.read(128)
                            if data:
                                if isinstance(data, bytes):
                                    self.receive_buffer += data
                                else:
                                    self.receive_buffer += data.encode('utf-8', errors='ignore')
                                    
                                if len(self.receive_buffer) > 512:
                                    # Try to parse any complete messages
                                    buffer_str = self.receive_buffer.decode('utf-8', errors='ignore')
                                    if '{' in buffer_str and '}' in buffer_str:
                                        start = buffer_str.find('{')
                                        end = buffer_str.rfind('}') + 1
                                        if start != -1 and end > start:
                                            message = buffer_str[start:end]
                                            self.handle_message(message)
                                    self.receive_buffer = b""
                        except:
                            pass
                        
                        time.sleep(0.1)
                
            except KeyboardInterrupt:
                print("Stopping controller...")
                self.update_display("ESP32", self.device_name[:12], "Stopped", "")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                error_msg = str(e)[:15]  # Truncate error message
                self.update_display("ESP32", self.device_name[:12], "Error", error_msg)
                self.connected = False
                self.close()
                time.sleep(5)
        
        self.close()

# Run the controller
if __name__ == "__main__":
    # Configuration for different devices
    # For the "controller" ESP32 (with potentiometer):
    # DEVICE_NAME = "controller"
    # LISTEN_TOPIC = "/receiver/status"
    
    # For the "receiver" ESP32 (with servo):
    # DEVICE_NAME = "receiver"  
    # LISTEN_TOPIC = "/controller/status"
    
    DEVICE_NAME = "controller"  # Change to "receiver" for the servo ESP32
    LISTEN_TOPIC = "/receiver/status"  # Change to "/controller/status" for the servo ESP32
    
    controller = ESP32ServoController(DEVICE_NAME, LISTEN_TOPIC)
    controller.run()
