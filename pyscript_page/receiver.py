import network
import usocket as socket
import ujson
import time
import ubinascii
import hashlib
from machine import Pin, SoftI2C
import servo
import ssd1306
import icons
import uselect

# WiFi credentials
SSID = "tufts_eecs"
PASSWORD = "------"

# WebSocket server details - using the same echo server
WS_HOST = "echo.websocket.org"
WS_PORT = 80
WS_PATH = "/"

class SmartMotorReceiver:
    def __init__(self):
        self.servo_motor = None
        self.display = None
        self.ws = None
        self.servo_pin = 2
        self.current_angle = 90
        self.last_data_received = 0
        self.connection_status = "Starting"
        self.display_update_interval = 500
        self.last_display_update = 0
        
        # Initialize components
        self.setup_display()
        self.setup_wifi()
        self.setup_servo()
    
    def setup_display(self):
        """Initialize OLED display"""
        try:
            i2c = SoftI2C(scl=Pin(7), sda=Pin(6))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))
            
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 15)
            self.display.text("Receiver", 30, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()
            print("OLED display initialized")
        except Exception as e:
            print(f"Display setup error: {e}")
            self.display = None
    
    def update_display(self, wifi_status, servo_angle, last_roll=None, connection_status="Unknown"):
        """Update OLED display with current status"""
        if not self.display:
            return
        
        try:
            self.display.fill(0)
            self.display.text("RECEIVER", 25, 0)
            self.display.text(f"WiFi: {wifi_status}", 0, 15)
            self.display.text(f"WS: {connection_status}", 0, 25)
            self.display.text(f"Servo: {servo_angle:.0f}deg", 0, 35)
            
            if last_roll is not None:
                self.display.text(f"Roll: {last_roll:.1f}", 0, 45)
            
            # Show time since last data
            time_since = time.ticks_diff(time.ticks_ms(), self.last_data_received) // 1000
            if time_since < 60:
                self.display.text(f"Last: {time_since}s", 0, 55)
            else:
                self.display.text("Last: >60s", 0, 55)
            
            self.display.show()
        except Exception as e:
            print(f"Display update error: {e}")
    
    def setup_wifi(self):
        """Connect to WiFi network"""
        print("SmartMotor Receiver Starting...")
        
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if not wlan.isconnected():
            if self.display:
                self.display.fill(0)
                self.display.text("Connecting WiFi", 10, 20)
                self.display.text(SSID[:16], 10, 35)
                self.display.show()
            
            print(f"Connecting to WiFi: {SSID}")
            
            try:
                wlan.connect(SSID, PASSWORD)
                
                max_wait = 30
                wait_count = 0
                
                while not wlan.isconnected() and wait_count < max_wait:
                    print(".", end="")
                    time.sleep(1)
                    wait_count += 1
                
                if wlan.isconnected():
                    config = wlan.ifconfig()
                    print(f"\nWiFi connected successfully!")
                    print(f"IP address: {config[0]}")
                    
                    if self.display:
                        self.display.fill(0)
                        self.display.text("WiFi Connected", 10, 20)
                        self.display.text(config[0], 10, 35)
                        self.display.show()
                        time.sleep(2)
                else:
                    print(f"\nWiFi connection failed")
                    
            except Exception as e:
                print(f"WiFi connection error: {e}")
        else:
            print("Already connected to WiFi")
    
    def setup_servo(self):
        """Initialize servo motor"""
        try:
            self.servo_motor = servo.Servo(Pin(self.servo_pin))
            self.move_servo(90)  # Start at center
            print(f"Servo initialized on pin {self.servo_pin} at 90°")
            
            if self.display:
                self.display.fill(0)
                self.display.text("Servo Ready", 25, 20)
                self.display.text("Position: 90", 25, 35)
                self.display.show()
                time.sleep(1)
        except Exception as e:
            print(f"Servo setup error: {e}")
            print("Make sure servo.py is uploaded to your ESP32")
    
    def move_servo(self, angle):
        """Move servo to specified angle"""
        if not self.servo_motor:
            print(f"Would move servo to: {angle}° (no servo available)")
            return
        
        try:
            # Clamp angle to valid range
            angle = max(0, min(180, angle))
            
            # Only move if angle changed significantly
            if abs(angle - self.current_angle) > 2:  # 2 degree threshold
                self.servo_motor.write_angle(degrees=angle)
                self.current_angle = angle
                print(f"✓ Moved servo to: {angle}°")
            
        except Exception as e:
            print(f"Servo movement error: {e}")
    
    def roll_to_servo_angle(self, roll):
        """Convert roll angle to servo angle"""
        # Map roll (-90 to +90) to servo (0 to 180)
        roll = max(-90, min(90, roll))
        servo_angle = 90 + roll  # Center at 90, direct mapping
        return max(0, min(180, servo_angle))
    
    def generate_websocket_key(self):
        """Generate a random WebSocket key"""
        import urandom
        key = ubinascii.b2a_base64(urandom.getrandbits(128).to_bytes(16, 'big')).decode().strip()
        return key
    
    def connect_websocket(self):
        """Connect to WebSocket server with proper handshake"""
        try:
            print(f"Connecting to WebSocket: {WS_HOST}:{WS_PORT}")
            
            # Create socket
            self.ws = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.ws.settimeout(10)
            
            # Get server address
            addr = socket.getaddrinfo(WS_HOST, WS_PORT)[0][-1]
            self.ws.connect(addr)
            
            # Generate WebSocket key
            ws_key = self.generate_websocket_key()
            
            # Send WebSocket handshake
            handshake = (
                f"GET {WS_PATH} HTTP/1.1\r\n"
                f"Host: {WS_HOST}:{WS_PORT}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Origin: http://esp32-receiver\r\n"
                "\r\n"
            )
            
            self.ws.send(handshake.encode())
            
            # Wait for handshake response
            response = self.ws.recv(1024).decode()
            print(f"WebSocket handshake response: {response[:200]}...")
            
            if "101 Switching Protocols" in response:
                print("✓ WebSocket connection established")
                self.connection_status = "Connected"
                self.ws.settimeout(0.1)  # Non-blocking for receiving
                return True
            else:
                print("✗ WebSocket handshake failed")
                self.ws.close()
                self.ws = None
                self.connection_status = "Handshake Failed"
                return False
                
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            if self.ws:
                self.ws.close()
            self.ws = None
            self.connection_status = "Connection Error"
            return False
    
    def parse_websocket_frame(self, frame):
        """Parse incoming WebSocket frame"""
        try:
            if len(frame) < 2:
                return None
            
            # First byte: FIN + RSV + Opcode
            first_byte = frame[0]
            fin = (first_byte & 0x80) >> 7
            opcode = first_byte & 0x0F
            
            # Second byte: MASK + Payload length
            second_byte = frame[1]
            masked = (second_byte & 0x80) >> 7
            payload_len = second_byte & 0x7F
            
            # Only handle text frames (opcode 1)
            if opcode != 1:
                return None
            
            offset = 2
            
            # Extended payload length
            if payload_len == 126:
                if len(frame) < offset + 2:
                    return None
                payload_len = int.from_bytes(frame[offset:offset+2], 'big')
                offset += 2
            elif payload_len == 127:
                if len(frame) < offset + 8:
                    return None
                payload_len = int.from_bytes(frame[offset:offset+8], 'big')
                offset += 8
            
            # Masking key (if present)
            if masked:
                if len(frame) < offset + 4:
                    return None
                mask = frame[offset:offset+4]
                offset += 4
            
            # Payload
            if len(frame) < offset + payload_len:
                return None
                
            payload = frame[offset:offset+payload_len]
            
            # Unmask payload if needed
            if masked:
                unmasked = bytearray()
                for i, byte in enumerate(payload):
                    unmasked.append(byte ^ mask[i % 4])
                payload = unmasked
            
            return payload.decode('utf-8')
            
        except Exception as e:
            print(f"Frame parsing error: {e}")
            return None
    
    def process_message(self, message_text):
        """Process incoming WebSocket message"""
        try:
            data = ujson.loads(message_text)
            
            if data.get("type") == "sensor_data" and data.get("device") == "controller":
                sensor_data = data.get("data", {})
                roll = sensor_data.get("roll", 0)
                
                print(f"📡 Received: Roll={roll:.1f}°")
                
                # Convert roll to servo angle and move servo
                servo_angle = self.roll_to_servo_angle(roll)
                self.move_servo(servo_angle)
                self.last_data_received = time.ticks_ms()
                
                return roll
                
        except Exception as e:
            print(f"Message processing error: {e}")
        
        return None
    
    def demo_mode(self):
        """Run servo demo when no connection"""
        if not self.servo_motor:
            print("Demo mode: No servo available")
            return
        
        print("Demo mode: Sweeping servo...")
        for angle in [45, 90, 135, 90]:
            self.move_servo(angle)
            time.sleep(1)
    
    def run(self):
        """Main loop with WebSocket communication"""
        print("Receiver running - listening for WebSocket messages...")
        print("Press Ctrl+C to stop")
        
        wlan = network.WLAN(network.STA_IF)
        last_roll = None
        
        try:
            while True:
                current_time = time.ticks_ms()
                
                # Check WiFi connection
                if not wlan.isconnected():
                    print("WiFi disconnected, reconnecting...")
                    self.setup_wifi()
                    time.sleep(2)
                    continue
                
                # Connect WebSocket if not connected
                if not self.ws:
                    print("WebSocket not connected, attempting to connect...")
                    self.connect_websocket()
                    time.sleep(2)
                    continue
                
                # Listen for WebSocket messages
                try:
                    # Use select to check if data is available
                    poll = uselect.poll()
                    poll.register(self.ws, uselect.POLLIN)
                    events = poll.poll(100)  # 100ms timeout
                    
                    if events:
                        # Receive data
                        frame = self.ws.recv(1024)
                        if frame:
                            message_text = self.parse_websocket_frame(frame)
                            if message_text:
                                received_roll = self.process_message(message_text)
                                if received_roll is not None:
                                    last_roll = received_roll
                                    self.connection_status = "Receiving"
                        
                except socket.timeout:
                    # Timeout is normal - continue loop
                    pass
                except Exception as e:
                    print(f"WebSocket receive error: {e}")
                    self.connection_status = "Receive Error"
                    if self.ws:
                        self.ws.close()
                    self.ws = None
                
                # Update display
                if time.ticks_diff(current_time, self.last_display_update) > self.display_update_interval:
                    wifi_status = "Connected" if wlan.isconnected() else "Disconnected"
                    self.update_display(wifi_status, self.current_angle, last_roll, self.connection_status)
                    self.last_display_update = current_time
                
                # Demo mode if no recent data
                if (time.ticks_diff(current_time, self.last_data_received) > 10000 and  # 10 seconds
                    not self.ws):
                    self.demo_mode()
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nReceiver stopped by user")
            if self.display:
                self.display.fill(0)
                self.display.text("STOPPED", 35, 30)
                self.display.show()
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(2)
        finally:
            # Cleanup
            if self.ws:
                self.ws.close()
                print("WebSocket connection closed")
            
            # Return servo to center
            if self.servo_motor:
                self.move_servo(90)
                print("Servo returned to center")

# Auto-run when uploaded to ESP32
if __name__ == "__main__":
    print("="*60)
    print("ESP32 SMART MOTOR RECEIVER - WebSocket Version")
    print("SETUP REQUIRED:")
    print("1. Set SSID and PASSWORD for your WiFi")
    print("2. Upload servo.py to ESP32")
    print("3. Connect servo to GPIO pin 2")
    print("4. Connect OLED display to I2C (SCL=7, SDA=6)")
    print("5. Save this file as 'main.py' to auto-run on boot")
    print("="*60)
    
    receiver = SmartMotorReceiver()
    receiver.run()
