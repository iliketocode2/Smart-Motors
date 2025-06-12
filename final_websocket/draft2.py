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
        
        # Hardware setup
        self.setup_hardware()
        self.setup_wifi()
        
        # Control variables
        self.servo_angle = 90
        self.last_servo_angle = 90
        self.potentiometer_angle = 90
        self.last_potentiometer_angle = 90
        
        # Improved potentiometer filtering
        self.knob_dead_zone = 3  # Reduced for better responsiveness
        self.knob_last_stable_angle = 90
        
        # Heartbeat system - use message-based timing instead of fixed intervals
        self.last_message_sent = 0
        self.last_message_received = 0
        self.message_timeout = 30000  # 30 seconds without messages = problem
        self.heartbeat_interval = 5000  # Send heartbeat every 5 seconds if no data
        self.partner_alive = False
        self.my_sequence = 0
        self.partner_sequence = 0
        
        # Improved buffer management
        self.receive_buffer = bytearray()  # Use bytearray for better memory efficiency
        self.max_buffer_size = 512  # Smaller buffer
        
        # Connection health monitoring
        self.connection_errors = 0
        self.max_connection_errors = 3
        self.last_successful_send = 0
        
        # Message rate limiting
        self.min_send_interval = 200  # Minimum 200ms between sends
        self.last_actual_send = 0
        
    def setup_hardware(self):
        """Setup hardware with better error handling"""
        try:
            # Setup display
            i2c = SoftI2C(scl=Pin(7), sda=Pin(6))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))
            self.display.fill(0)
            self.display.text("ESP32", 45, 10)
            self.display.text(self.device_name[:10], 25, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()
            print("Display initialized")
        except Exception as e:
            print(f"Display setup failed: {e}")
            self.display = None
        
        # Setup servo (for receiver ESP32)
        if self.device_name == "receiver":
            try:
                self.servo = servo.Servo(Pin(2))
                self.servo.write_angle(90)
                print("Servo initialized on Pin 2")
            except Exception as e:
                print(f"Servo setup failed: {e}")
                self.servo = None
        else:
            self.servo = None
        
        # Setup potentiometer (for controller ESP32)
        if self.device_name == "controller":
            try:
                self.knob = ADC(Pin(3))
                self.knob.atten(ADC.ATTN_11DB)
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
        """Update display with status"""
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
        
    def setup_wifi(self):
        print("Connecting to WiFi...")
        self.update_display("ESP32", self.device_name[:10], "WiFi...", "Connecting")
        
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
            ip_short = ip[:15] if len(ip) > 15 else ip
            self.update_display("ESP32", self.device_name[:10], "WiFi OK", ip_short)
            time.sleep(2)
            return True
        else:
            print("\nWiFi connection failed!")
            self.update_display("ESP32", self.device_name[:10], "WiFi FAIL", "Check creds")
            return False
    
    def generate_websocket_key(self):
        key_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
        return ubinascii.b2a_base64(key_bytes).decode().strip()
    
    def connect_websocket(self):
        """Original reliable connection logic with memory improvements"""
        try:
            print("Connecting to WebSocket...")
            self.update_display("ESP32", self.device_name[:10], "WebSocket", "Connecting...")
            
            # Reset connection state
            self.connection_errors = 0
            self.last_message_received = time.ticks_ms()
            self.last_message_sent = time.ticks_ms()
            
            addr_info = socket.getaddrinfo(WS_HOST, WS_PORT)
            addr = addr_info[0][-1]
            
            # Create SSL socket - KEEP ORIGINAL LOGIC
            raw_sock = socket.socket()
            raw_sock.settimeout(10)  # Set timeout for connection
            raw_sock.connect(addr)
            self.ws = ussl.wrap_socket(raw_sock, server_hostname=WS_HOST)
            
            # WebSocket handshake - ORIGINAL LOGIC
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
            
            # Read handshake response - ORIGINAL LOGIC
            response = b""
            while b'\r\n\r\n' not in response:
                chunk = self.ws.read(1024)
                if not chunk:
                    break
                response += chunk
            
            if b"101 Switching Protocols" in response:
                print("WebSocket connected successfully!")
                self.update_display("ESP32", self.device_name[:10], "Connected", "Ready")
                self.connected = True
                self.receive_buffer = bytearray()  # Clear buffer
                
                # Initialize timing
                current_time = time.ticks_ms()
                self.last_message_received = current_time
                self.last_message_sent = current_time
                self.last_successful_send = current_time
                
                # Force garbage collection
                gc.collect()
                return True
            else:
                print("WebSocket handshake failed")
                self.update_display("ESP32", self.device_name[:10], "WS Failed", "Handshake")
                return False
                
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            error_str = str(e)[:12]
            self.update_display("ESP32", self.device_name[:10], "WS Error", error_str)
            return False
    
    def send_message(self, topic, value):
        """Send message with improved error handling and rate limiting"""
        if not self.connected:
            return False
        
        current_time = time.ticks_ms()
        
        # Rate limiting - prevent flooding
        if time.ticks_diff(current_time, self.last_actual_send) < self.min_send_interval:
            return False
            
        try:
            # Create message
            message = {
                "topic": topic,
                "value": value
            }
            
            json_data = json.dumps(message)
            payload = json_data.encode('utf-8')
            length = len(payload)
            
            # Limit message size
            if length > 800:  # Even smaller limit
                print("Message too large, skipping")
                return False
            
            # Create WebSocket frame
            frame = bytearray()
            frame.append(0x81)  # FIN=1, opcode=1 (text)
            
            # Generate mask key
            mask_key = bytearray([urandom.getrandbits(8) for _ in range(4)])
            
            # Add length and mask bit
            if length <= 125:
                frame.append(0x80 | length)
            elif length < 65536:
                frame.append(0x80 | 126)
                frame.extend(length.to_bytes(2, 'big'))
            else:
                return False  # Message too large
            
            # Add mask key
            frame.extend(mask_key)
            
            # Mask and add payload
            for i in range(length):
                frame.append(payload[i] ^ mask_key[i % 4])
            
            # Send with error handling
            self.ws.write(frame)
            
            # Update timing and reset error count on success
            self.last_message_sent = current_time
            self.last_actual_send = current_time
            self.last_successful_send = current_time
            self.connection_errors = 0
            self.my_sequence += 1
            
            print(f"Sent #{self.my_sequence}: {topic} = {str(value)[:50]}")
            
            # Periodic garbage collection
            if self.my_sequence % 10 == 0:
                gc.collect()
            
            return True
            
        except Exception as e:
            print(f"Send error: {e}")
            self.connection_errors += 1
            if self.connection_errors >= self.max_connection_errors:
                print("Too many send errors, marking as disconnected")
                self.connected = False
            return False
    
    def safe_decode(self, data):
        """Safely decode bytes to string"""
        try:
            if isinstance(data, bytes):
                return data.decode('utf-8', 'ignore')  # Ignore invalid UTF-8
            elif isinstance(data, bytearray):
                return bytes(data).decode('utf-8', 'ignore')
            else:
                return str(data)
        except:
            return ""
    
    def extract_json_messages(self, buffer):
        """Extract complete JSON messages from buffer with improved memory management"""
        messages = []
        
        try:
            text = self.safe_decode(buffer)
            if not text:
                return messages
            
            start = 0
            while start < len(text):
                # Find start of JSON object
                json_start = text.find('{', start)
                if json_start == -1:
                    break
                
                # Find matching closing brace
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
                    # Incomplete JSON - keep remaining for next time
                    remaining = text[json_start:].encode('utf-8')
                    self.receive_buffer = bytearray(remaining)
                    break
            
            # If we processed everything, clear the buffer
            if start >= len(text):
                self.receive_buffer = bytearray()
            
        except Exception as e:
            print(f"JSON extraction error: {e}")
            # Clear corrupted buffer
            self.receive_buffer = bytearray()
        
        return messages
    
    def handle_message(self, message_str):
        """Handle incoming message with better error handling"""
        try:
            self.last_message_received = time.ticks_ms()
            self.partner_alive = True
            
            # Parse CEEO channel message
            channel_msg = json.loads(message_str)
            
            if channel_msg.get('type') == 'welcome':
                print("Channel connection confirmed")
                return
            
            if channel_msg.get('type') == 'data' and 'payload' in channel_msg:
                payload_str = channel_msg['payload']
                payload = json.loads(payload_str)
                topic = payload.get('topic', '')
                value = payload.get('value', {})
                
                # Track partner sequence if available
                if isinstance(value, dict) and 'sequence' in value:
                    self.partner_sequence = value['sequence']
                
                print(f"Received #{self.partner_sequence}: {topic}")
                
                # Check if this message is for us
                if topic == self.listen_topic:
                    self.process_message(value)
                    
        except Exception as e:
            print(f"Message handling error: {e}")
    
    def process_message(self, data):
        """Process received data"""
        if not isinstance(data, dict):
            return
        
        if self.device_name == "receiver":
            # Receiver: move servo based on controller's potentiometer
            if 'potentiometer_angle' in data:
                angle = data['potentiometer_angle']
                if isinstance(angle, (int, float)):
                    angle = max(0, min(180, int(angle)))
                    
                    if self.move_servo(angle):
                        self.servo_angle = angle
                        self.update_display(
                            "RECEIVER",
                            "Servo Motor",
                            f"Angle: {angle}°",
                            f"Rx: {self.partner_sequence}"
                        )
        
        elif self.device_name == "controller":
            # Controller: display receiver's servo position
            if 'servo_angle' in data:
                angle = data['servo_angle']
                self.update_display(
                    "CONTROLLER",
                    "Remote Servo",
                    f"Angle: {angle}°",
                    f"Rx: {self.partner_sequence}"
                )
    
    def read_potentiometer(self):
        """Read potentiometer with simple filtering"""
        if not self.knob_available:
            return 90
        
        try:
            # Take 3 quick readings and average
            readings = []
            for _ in range(3):
                readings.append(self.knob.read())
                time.sleep(0.001)
            
            average_raw = sum(readings) / len(readings)
            angle = int((180.0 / 4095.0) * average_raw)
            angle = max(0, min(180, angle))
            
            # Apply dead zone
            if abs(angle - self.knob_last_stable_angle) > self.knob_dead_zone:
                self.knob_last_stable_angle = angle
            
            return self.knob_last_stable_angle
            
        except Exception as e:
            print(f"Potentiometer read error: {e}")
            return self.knob_last_stable_angle
    
    def move_servo(self, angle):
        """Move servo to specified angle"""
        if self.servo:
            try:
                self.servo.write_angle(angle)
                time.sleep(0.05)  # Shorter delay
                return True
            except Exception as e:
                print(f"Servo move error: {e}")
                return False
        return False
    
    def check_connection_health(self):
        """Check if connection is healthy and send heartbeat if needed"""
        current_time = time.ticks_ms()
        
        # Check if we haven't received messages in too long
        if time.ticks_diff(current_time, self.last_message_received) > self.message_timeout:
            print("No messages received for too long, connection may be dead")
            return False
        
        # Send heartbeat if we haven't sent anything recently
        if time.ticks_diff(current_time, self.last_message_sent) > self.heartbeat_interval:
            heartbeat_data = {
                "device": self.device_name,
                "heartbeat": True,
                "sequence": self.my_sequence,
                "timestamp": current_time,
                "partner_seq": self.partner_sequence
            }
            
            if self.send_message(self.send_topic, heartbeat_data):
                print(f"Sent heartbeat #{self.my_sequence}")
            else:
                print("Heartbeat send failed")
                return False
        
        return True
    
    def listen_for_messages(self):
        """Listen for incoming messages with improved buffer management"""
        print("Starting message listener...")
        
        while self.running and self.connected:
            try:
                # Check connection health
                if not self.check_connection_health():
                    print("Connection health check failed")
                    self.connected = False
                    break
                
                # Try to read data
                try:
                    data = self.ws.read(256)  # Small chunks
                    if data:
                        # Add to buffer
                        self.receive_buffer.extend(data)
                        
                        # Prevent buffer overflow
                        if len(self.receive_buffer) > self.max_buffer_size:
                            # Keep only the last part
                            self.receive_buffer = self.receive_buffer[-256:]
                        
                        # Process complete messages
                        messages = self.extract_json_messages(self.receive_buffer)
                        for message in messages:
                            self.handle_message(message)
                            
                except OSError as e:
                    # Normal timeout - continue
                    pass
                except Exception as e:
                    print(f"Read error: {e}")
                    self.connection_errors += 1
                    if self.connection_errors >= self.max_connection_errors:
                        print("Too many read errors")
                        self.connected = False
                        break
                
                time.sleep(0.05)  # Small delay
                
            except Exception as e:
                print(f"Listen loop error: {e}")
                self.connected = False
                break
    
    def sender_loop(self):
        """Main sending loop - responds to changes rather than fixed timing"""
        print("Starting sender loop...")
        last_check_time = 0
        
        while self.running:
            try:
                if not self.connected:
                    time.sleep(1)
                    continue
                
                current_time = time.ticks_ms()
                
                # Check for changes every 100ms
                if time.ticks_diff(current_time, last_check_time) > 100:
                    
                    if self.device_name == "controller":
                        # Send potentiometer reading when it changes
                        angle = self.read_potentiometer()
                        
                        # Send if angle changed significantly
                        if abs(angle - self.last_potentiometer_angle) > 2:
                            data = {
                                "device": "controller",
                                "potentiometer_angle": angle,
                                "sequence": self.my_sequence,
                                "timestamp": current_time,
                                "type": "data"
                            }
                            
                            if self.send_message(self.send_topic, data):
                                self.last_potentiometer_angle = angle
                                self.update_display(
                                    "CONTROLLER",
                                    "Potentiometer",
                                    f"Angle: {angle}°",
                                    f"Tx: {self.my_sequence}"
                                )
                    
                    elif self.device_name == "receiver":
                        # Send servo status when it changes
                        if self.servo_angle != self.last_servo_angle:
                            data = {
                                "device": "receiver", 
                                "servo_angle": self.servo_angle,
                                "sequence": self.my_sequence,
                                "timestamp": current_time,
                                "type": "status"
                            }
                            
                            if self.send_message(self.send_topic, data):
                                self.last_servo_angle = self.servo_angle
                                self.update_display(
                                    "RECEIVER",
                                    "Servo Status",
                                    f"Angle: {self.servo_angle}°",
                                    f"Tx: {self.my_sequence}"
                                )
                    
                    last_check_time = current_time
                
                time.sleep(0.05)
                
            except Exception as e:
                print(f"Sender error: {e}")
                time.sleep(1)
    
    def close(self):
        """Clean shutdown"""
        print("Closing connection...")
        self.running = False
        self.connected = False
        
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
        
        # Return servo to center if this is receiver
        if self.device_name == "receiver" and self.servo:
            self.move_servo(90)
        
        # Clear buffers
        self.receive_buffer = bytearray()
        gc.collect()
    
    def run(self):
        """Main run loop with improved error recovery"""
        print(f"Starting ESP32 {self.device_name}...")
        print(f"Will send to: {self.send_topic}")
        print(f"Will listen to: {self.listen_topic}")
        
        retry_count = 0
        max_retries = 5
        
        while self.running and retry_count < max_retries:
            try:
                if not self.connected:
                    self.update_display("ESP32", self.device_name[:10], "Connecting...", f"Try {retry_count+1}")
                    
                    if not self.connect_websocket():
                        retry_count += 1
                        print(f"Connection failed, retry {retry_count}/{max_retries} in 5 seconds...")
                        time.sleep(5)
                        continue
                    else:
                        retry_count = 0  # Reset on successful connection
                
                # Start sender thread if available
                try:
                    _thread.start_new_thread(self.sender_loop, ())
                    print("Sender thread started")
                    
                    # Main thread handles receiving
                    self.listen_for_messages()
                    
                except:
                    print("Threading not available, running single-threaded")
                    # Single-threaded fallback - simplified
                    last_action_time = 0
                    
                    while self.running and self.connected:
                        current_time = time.ticks_ms()
                        
                        if not self.check_connection_health():
                            self.connected = False
                            break
                        
                        # Handle data every 250ms
                        if time.ticks_diff(current_time, last_action_time) > 250:
                            # Send data based on device type
                            if self.device_name == "controller":
                                angle = self.read_potentiometer()
                                if abs(angle - self.last_potentiometer_angle) > 2:
                                    data = {
                                        "device": "controller",
                                        "potentiometer_angle": angle,
                                        "sequence": self.my_sequence,
                                        "timestamp": current_time
                                    }
                                    
                                    if self.send_message(self.send_topic, data):
                                        self.last_potentiometer_angle = angle
                                        self.update_display(
                                            "CONTROLLER",
                                            "Single Thread",
                                            f"Angle: {angle}°",
                                            f"Tx: {self.my_sequence}"
                                        )
                                    else:
                                        self.connected = False
                                        break
                            
                            last_action_time = current_time
                        
                        # Try to receive
                        try:
                            data = self.ws.read(128)
                            if data:
                                self.receive_buffer.extend(data)
                                if len(self.receive_buffer) > 256:
                                    messages = self.extract_json_messages(self.receive_buffer)
                                    for message in messages:
                                        self.handle_message(message)
                        except OSError:
                            pass
                        
                        time.sleep(0.1)
                
            except KeyboardInterrupt:
                print("Keyboard interrupt - stopping...")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.update_display("ESP32", self.device_name[:10], "Error", str(e)[:12])
                self.connected = False
                retry_count += 1
                time.sleep(2)
        
        if retry_count >= max_retries:
            print("Max retries reached, giving up")
            self.update_display("ESP32", self.device_name[:10], "Failed", "Max retries")
        
        self.close()

# Run the controller
if __name__ == "__main__":
    # Configuration for different devices
    DEVICE_NAME = "controller"  # Change to "receiver" for the servo ESP32
    LISTEN_TOPIC = "/receiver/status"  # Change to "/controller/status" for the servo ESP32
    
    controller = ESP32ServoController(DEVICE_NAME, LISTEN_TOPIC)
    controller.run()
