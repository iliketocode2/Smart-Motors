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
        
        # Simplified receive buffer management
        self.receive_buffer = ""
        self.max_buffer_size = 1024  # Smaller buffer size
        
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
    
    def safe_decode(self, data):
        """Safely decode bytes to string - FIXED for MicroPython"""
        try:
            if isinstance(data, bytes):
                # Try to decode as UTF-8
                return data.decode('utf-8')
            elif isinstance(data, str):
                return data
            else:
                return str(data)
        except Exception:  # Catch any decode error in MicroPython
            # Handle decode errors by replacing invalid characters
            if isinstance(data, bytes):
                result = ""
                for byte_val in data:
                    if 32 <= byte_val <= 126:  # Printable ASCII
                        result += chr(byte_val)
                    else:
                        result += "?"
                return result
            else:
                return str(data)
    
    def extract_json_messages(self, text):
        """Extract complete JSON messages from text buffer"""
        messages = []
        start = 0
        
        while True:
            # Find start of JSON object
            json_start = text.find('{', start)
            if json_start == -1:
                break
            
            # Count braces to find complete JSON
            brace_count = 0
            json_end = -1
            
            for i in range(json_start, len(text)):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            
            if json_end != -1:
                json_str = text[json_start:json_end]
                messages.append(json_str)
                start = json_end
            else:
                # Incomplete JSON, save remaining text
                self.receive_buffer = text[json_start:]
                break
        
        if start < len(text) and json_start == -1:
            # No JSON found, keep last part of buffer
            self.receive_buffer = text[start:]
        elif json_end != -1 and json_end == len(text):
            # All text processed
            self.receive_buffer = ""
        
        return messages
    
    def handle_message(self, message_str):
        """Handle incoming CEEO channel message - IMPROVED"""
        try:
            print(f"Raw message: {message_str[:100]}...")  # Debug: show first 100 chars
            
            # Parse CEEO channel message
            channel_msg = json.loads(message_str)
            
            if channel_msg.get('type') == 'welcome':
                print("Channel connection confirmed")
                return
            
            if channel_msg.get('type') == 'data' and 'payload' in channel_msg:
                payload_str = channel_msg['payload']
                print(f"Payload string: {payload_str}")
                
                # Parse the inner payload
                payload = json.loads(payload_str)
                topic = payload.get('topic', '')
                value = payload.get('value', {})
                
                print(f"Parsed - Topic: {topic}, Value: {value}")
                
                # Check if this message is for us
                if topic == self.listen_topic:
                    print(f"Message is for us! Processing...")
                    self.process_message(value)
                else:
                    print(f"Message not for us. Expected: {self.listen_topic}, Got: {topic}")
                    
        except Exception as e:
            print(f"Message handling error: {e}")
    
    def process_message(self, data):
        """Process received data based on device type - IMPROVED"""
        print(f"Processing message data: {data}")
        
        if not isinstance(data, dict):
            print(f"Data is not dict, got: {type(data)}")
            return
        
        if self.device_name == "receiver":
            # Receiver: move servo based on controller's potentiometer
            if 'potentiometer_angle' in data:
                angle = data['potentiometer_angle']
                print(f"Received potentiometer angle: {angle}")
                
                if isinstance(angle, (int, float)):
                    angle = max(0, min(180, int(angle)))
                    print(f"Moving servo to {angle}°")
                    
                    if self.move_servo(angle):
                        self.servo_angle = angle
                        self.update_display(
                            "RECEIVER",
                            "Servo Motor",
                            f"Angle: {angle}°",
                            "Updated!"
                        )
                    else:
                        print("Failed to move servo")
                else:
                    print(f"Invalid angle type: {type(angle)}")
            else:
                print("No potentiometer_angle in data")
        
        elif self.device_name == "controller":
            # Controller: display receiver's servo position
            if 'servo_angle' in data:
                angle = data['servo_angle']
                print(f"Receiver servo at {angle}°")
                self.update_display(
                    "CONTROLLER",
                    "Remote Servo",
                    f"Angle: {angle}°",
                    "Received!"
                )
    
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
        """Listen for incoming messages - SIMPLIFIED and FIXED"""
        while self.running and self.connected:
            try:
                # Read data from WebSocket
                data = self.ws.read(512)  # Smaller buffer
                if data:
                    # Convert to string and add to buffer
                    text_data = self.safe_decode(data)
                    self.receive_buffer += text_data
                    
                    # Limit buffer size
                    if len(self.receive_buffer) > self.max_buffer_size:
                        # Keep only the last part of buffer
                        self.receive_buffer = self.receive_buffer[-512:]
                    
                    # Extract and process complete JSON messages
                    messages = self.extract_json_messages(self.receive_buffer)
                    for message in messages:
                        self.handle_message(message)
                
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
                
                # Send data every 1000ms (1 second) - slower to reduce network load
                if time.ticks_diff(current_time, last_send_time) > 1000:
                    
                    if self.device_name == "controller":
                        # Send potentiometer reading
                        angle = self.read_potentiometer()
                        
                        # Only send if angle changed significantly
                        if abs(angle - self.last_potentiometer_angle) > 2:
                            data = {
                                "device": "controller",
                                "potentiometer_angle": angle,
                                "timestamp": time.ticks_ms(),
                                "count": send_count
                            }
                            
                            print(f"Sending controller data: {data}")
                            if self.send_message(self.send_topic, data):
                                self.last_potentiometer_angle = angle
                                send_count += 1
                                self.update_display(
                                    "CONTROLLER",
                                    "Potentiometer",
                                    f"Angle: {angle}°",
                                    f"Sent: {send_count}"
                                )
                    
                    elif self.device_name == "receiver":
                        # Send servo status
                        data = {
                            "device": "receiver", 
                            "servo_angle": self.servo_angle,
                            "timestamp": time.ticks_ms(),
                            "count": send_count
                        }
                        
                        print(f"Sending receiver data: {data}")
                        if self.send_message(self.send_topic, data):
                            send_count += 1
                            self.update_display(
                                "RECEIVER",
                                "Servo Status",
                                f"Angle: {self.servo_angle}°",
                                f"Sent: {send_count}"
                            )
                    
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
                
                # Try to start sender thread
                try:
                    _thread.start_new_thread(self.sender_loop, ())
                    print("Sender thread started")
                    # Main loop handles receiving
                    self.listen_for_messages()
                except:
                    print("Threading not available, running single-threaded")
                    # Single-threaded fallback
                    send_count = 0
                    last_send_time = 0
                    
                    while self.running and self.connected:
                        current_time = time.ticks_ms()
                        
                        # Send every 1000ms
                        if time.ticks_diff(current_time, last_send_time) > 1000:
                            if self.device_name == "controller":
                                new_pot_angle = self.read_potentiometer()
                                if abs(new_pot_angle - self.last_potentiometer_angle) > 2:
                                    controller_data = {
                                        "device": "controller",
                                        "potentiometer_angle": new_pot_angle,
                                        "timestamp": current_time,
                                        "count": send_count
                                    }
                                    
                                    print(f"Single-thread sending: {controller_data}")
                                    success = self.send_message(self.send_topic, controller_data)
                                    if success:
                                        self.last_potentiometer_angle = new_pot_angle
                                        send_count += 1
                                        self.update_display(
                                            "CONTROLLER",
                                            "Potentiometer",
                                            f"Angle: {new_pot_angle}°",
                                            f"Sent: {send_count}"
                                        )
                                    else:
                                        self.connected = False
                                        break
                                        
                            elif self.device_name == "receiver":
                                receiver_data = {
                                    "device": "receiver",
                                    "servo_angle": self.servo_angle,
                                    "timestamp": current_time,
                                    "count": send_count
                                }
                                
                                print(f"Single-thread sending: {receiver_data}")
                                success = self.send_message(self.send_topic, receiver_data)
                                if success:
                                    send_count += 1
                                    self.update_display(
                                        "RECEIVER",
                                        "Servo Status",
                                        f"Angle: {self.servo_angle}°",
                                        f"Sent: {send_count}"
                                    )
                                else:
                                    self.connected = False
                                    break
                            
                            last_send_time = current_time
                            gc.collect()
                        
                        # Try to receive data
                        try:
                            data = self.ws.read(256)
                            if data:
                                text_data = self.safe_decode(data)
                                self.receive_buffer += text_data
                                
                                # Limit buffer size
                                if len(self.receive_buffer) > 512:
                                    messages = self.extract_json_messages(self.receive_buffer)
                                    for message in messages:
                                        self.handle_message(message)
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
