import network
import urequests as requests
import ujson
import time
from machine import Pin, SoftI2C
import servo
import ssd1306
import icons

# WiFi credentials
SSID = "tufts_eecs"
PASSWORD = "------"

# Channel endpoint - try different approaches
CHANNEL_URL = "https://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon"

class SmartMotorReceiver:
    def __init__(self):
        self.servo_motor = None
        self.display = None
        self.servo_pin = 2
        self.current_angle = 90
        self.last_poll = 0
        self.poll_interval = 1500  # Poll every 1.5 seconds
        self.display_update_interval = 500  # Update display every 500ms
        self.last_display_update = 0
        self.last_data_received = 0
        self.connection_status = "Starting"
        
        # Initialize components
        self.setup_display()
        self.setup_wifi()
        self.setup_servo()
    
    def setup_display(self):
        """Initialize OLED display"""
        try:
            # Initialize I2C for OLED (adjust pins as needed)
            i2c = SoftI2C(scl = Pin(7), sda = Pin(6))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))
            
            # Startup screen
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
            self.display.text(f"Servo: {servo_angle:.0f}deg", 0, 25)
            
            if last_roll is not None:
                self.display.text(f"Roll: {last_roll:.1f}", 0, 35)
                
            # Show connection status
            self.display.text(f"Conn: {connection_status}", 0, 45)
            
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
                if SSID == "YOUR_WIFI_SSID" or PASSWORD == "YOUR_WIFI_PASSWORD":
                    print("ERROR: Please set your actual SSID and PASSWORD!")
                    if self.display:
                        self.display.fill(0)
                        self.display.text("WiFi Setup", 20, 20)
                        self.display.text("Required!", 25, 35)
                        self.display.show()
                    return
                
                wlan.connect(SSID, PASSWORD)
                
                # Wait for connection
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
                    if self.display:
                        self.display.fill(0)
                        self.display.text("WiFi Failed", 20, 30)
                        self.display.show()
                    
            except Exception as e:
                print(f"WiFi connection error: {e}")
        else:
            print("Already connected to WiFi")
            config = wlan.ifconfig()
            print(f"IP address: {config[0]}")
    
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
        """Convert roll angle to servo angle with better mapping"""
        # Method 1: Map roll (-90 to +90) to servo (0 to 180)
        # Clamp roll to reasonable range first
        roll = max(-90, min(90, roll))
        servo_angle = 90 + roll  # Center at 90, direct mapping
        
        return max(0, min(180, servo_angle))
    
    def poll_for_messages(self):
        """Poll HTTP endpoint for new messages - try multiple approaches"""
        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            print("WiFi not connected, cannot poll")
            self.connection_status = "No WiFi"
            return None
        
        # Try different approaches to get data
        approaches = [
            ("GET", {}),
            ("GET", {"Accept": "application/json"}),
            ("POST", {"Content-Type": "application/json", "Accept": "application/json"}),
        ]
        
        for method, headers in approaches:
            try:
                print(f"Trying {method} request...")
                
                if method == "GET":
                    response = requests.get(CHANNEL_URL, headers=headers, timeout=8)
                else:
                    # For POST, send a simple query message
                    query_data = {"action": "get_messages", "topic": "hackathon"}
                    response = requests.post(CHANNEL_URL, 
                                           data=ujson.dumps(query_data) if headers.get("Content-Type") == "application/json" else None,
                                           headers=headers, 
                                           timeout=8)
                
                print(f"Response status: {response.status_code}")
                print(f"Response headers: {dict(response.headers) if hasattr(response, 'headers') else 'No headers'}")
                
                if response.status_code == 200:
                    response_text = response.text
                    print(f"Response length: {len(response_text)}")
                    print(f"Response start: {response_text[:100]}...")
                    
                    # Check if it's HTML (error page) or JSON
                    if response_text.strip().startswith('<!DOCTYPE html>') or response_text.strip().startswith('<html'):
                        print("Received HTML instead of JSON - this endpoint might not support this method")
                        self.connection_status = "HTML Response"
                        response.close()
                        continue
                    
                    # Try to parse as JSON
                    try:
                        data = ujson.loads(response_text)
                        print(f"Successfully parsed JSON with {method}")
                        self.connection_status = "Connected"
                        response.close()
                        return self.process_json_data(data)
                    except ValueError as json_error:
                        print(f"JSON parse error with {method}: {json_error}")
                        self.connection_status = "Parse Error"
                        
                else:
                    print(f"{method} failed with status {response.status_code}")
                    self.connection_status = f"HTTP {response.status_code}"
                
                response.close()
                
            except Exception as e:
                print(f"{method} request error: {e}")
                self.connection_status = "Network Error"
        
        return None
    
    def process_json_data(self, data):
        """Process the JSON data received from the server"""
        try:
            # Handle different response formats
            messages = []
            if isinstance(data, list):
                messages = data
            elif isinstance(data, dict):
                if 'messages' in data:
                    messages = data['messages']
                elif 'data' in data:
                    # Handle the format we're sending from controller
                    if data.get('type') == 'sensor_data':
                        messages = [data]
                else:
                    messages = [data]  # Single message
            
            # Process messages
            if messages:
                # Get the most recent accelerometer message
                latest_data = None
                for msg in reversed(messages):  # Start from most recent
                    if isinstance(msg, dict):
                        # Look for our sensor data format
                        if msg.get('type') == 'sensor_data' and 'data' in msg:
                            latest_data = msg['data']
                            break
                        # Or the original format
                        elif msg.get('topic') == '/SM/accel':
                            latest_data = {'roll': msg.get('value', 0)}
                            break
                
                if latest_data and 'roll' in latest_data:
                    roll_value = latest_data['roll']
                    device = latest_data.get('device_id', 'unknown')
                    
                    print(f"📡 Received from {device}: Roll={roll_value:.1f}°")
                    
                    # Convert and move servo
                    if isinstance(roll_value, (int, float)):
                        servo_angle = self.roll_to_servo_angle(roll_value)
                        self.move_servo(servo_angle)
                        self.last_data_received = time.ticks_ms()
                        return roll_value
                else:
                    print("No sensor data found in messages")
            else:
                print("No messages in response")
                
        except Exception as parse_error:
            print(f"Data processing error: {parse_error}")
        
        return None
    
    def demo_mode(self):
        """Run servo demo when no WiFi"""
        if not self.servo_motor:
            print("Demo mode: No servo available")
            if self.display:
                self.display.fill(0)
                self.display.text("DEMO MODE", 25, 20)
                self.display.text("No Servo", 30, 35)
                self.display.show()
            time.sleep(2)
            return
        
        print("Demo mode: Sweeping servo...")
        if self.display:
            self.display.fill(0)
            self.display.text("DEMO MODE", 25, 10)
            self.display.text("Servo Sweep", 20, 25)
            self.display.show()
        
        # Slow sweep
        for angle in [45, 90, 135, 90]:
            self.move_servo(angle)
            time.sleep(1)
    
    def run(self):
        """Main loop"""
        print("Receiver running - polling for accelerometer data...")
        print("Press Ctrl+C to stop")
        
        wlan = network.WLAN(network.STA_IF)
        last_roll = None
        
        try:
            while True:
                current_time = time.ticks_ms()
                
                if wlan.isconnected():
                    # Poll for new data
                    if time.ticks_diff(current_time, self.last_poll) > self.poll_interval:
                        received_roll = self.poll_for_messages()
                        if received_roll is not None:
                            last_roll = received_roll
                        self.last_poll = current_time
                    
                    # Update display
                    if time.ticks_diff(current_time, self.last_display_update) > self.display_update_interval:
                        self.update_display("Connected", self.current_angle, last_roll, self.connection_status)
                        self.last_display_update = current_time
                    
                    time.sleep(0.2)  # Short delay
                
                else:
                    # Demo mode when no WiFi
                    if time.ticks_diff(current_time, self.last_display_update) > self.display_update_interval:
                        self.update_display("Disconnected", self.current_angle, None, "No WiFi")
                        self.last_display_update = current_time
                    
                    self.demo_mode()
                
        except KeyboardInterrupt:
            print("\nReceiver stopped by user")
            if self.display:
                self.display.fill(0)
                self.display.text("STOPPED", 35, 30)
                self.display.show()
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(2)
        
        # Cleanup
        if self.servo_motor:
            self.move_servo(90)  # Return to center
            print("Servo returned to center")

# Auto-run when uploaded to ESP32
if __name__ == "__main__":
    print("="*60)
    print("ESP32 SMART MOTOR RECEIVER - Fixed Version")
    print("SETUP REQUIRED:")
    print("1. Set SSID and PASSWORD for your WiFi")
    print("2. Upload servo.py to ESP32")
    print("3. Connect servo to GPIO pin 2")
    print("4. Connect OLED display to I2C (SCL=22, SDA=21)")
    print("5. Save this file as 'main.py' to auto-run on boot")
    print("="*60)
    
    receiver = SmartMotorReceiver()
    receiver.run()
