import network
import socket
import urequests as requests
import ujson
import time
import ubinascii
import hashlib
from machine import Pin, SoftI2C
import sensors  # Using your existing sensors module
import ssd1306  # For OLED display
import icons

# WiFi credentials
SSID = "tufts_eecs"
PASSWORD = "------"

# Channel endpoint - using a different approach
CHANNEL_URL = "https://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon"

class SmartMotorController:
    def __init__(self):
        self.sensor_system = None
        self.display = None
        self.last_send = 0
        self.send_interval = 2000  # Send every 2 seconds
        self.display_update_interval = 500  # Update display every 500ms
        self.last_display_update = 0
        
        # Initialize components
        self.setup_display()
        self.setup_wifi()
        self.setup_sensors()
    
    def setup_display(self):
        """Initialize OLED display"""
        try:
            # Initialize I2C for OLED (adjust pins as needed)
            i2c = SoftI2C(scl = Pin(7), sda = Pin(6))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))
            
            # Startup screen
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 15)
            self.display.text("Controller", 25, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()
            print("OLED display initialized")
        except Exception as e:
            print(f"Display setup error: {e}")
            self.display = None
    
    def update_display(self, status, wifi_status, sensor_data=None):
        """Update OLED display with current status"""
        if not self.display:
            return
        
        try:
            self.display.fill(0)
            self.display.text("CONTROLLER", 20, 0)
            self.display.text(f"WiFi: {wifi_status}", 0, 15)
            self.display.text(f"Status: {status}", 0, 25)
            
            if sensor_data:
                self.display.text(f"Roll: {sensor_data['roll']:.1f}", 0, 35)
                self.display.text(f"Pitch: {sensor_data['pitch']:.1f}", 0, 45)
                self.display.text(f"Send: {'OK' if sensor_data.get('sent') else 'FAIL'}", 0, 55)
            
            self.display.show()
        except Exception as e:
            print(f"Display update error: {e}")
    
    def setup_wifi(self):
        """Connect to WiFi network"""
        print("SmartMotor Controller Starting...")
        
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
    
    def setup_sensors(self):
        """Initialize sensor system"""
        try:
            print("Initializing sensor system...")
            self.sensor_system = sensors.SENSORS()
            print("Sensor system initialized successfully")
        except Exception as e:
            print(f"Sensor setup error: {e}")
            self.sensor_system = None
    
    def send_data_websocket_style(self):
        """Send data using a WebSocket-like message format"""
        if not self.sensor_system:
            return False
        
        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            print("WiFi not connected")
            return False
        
        try:
            # Read sensor data
            x, y, z = self.sensor_system.readaccel()
            roll, pitch = self.sensor_system.readroll()
            
            # Create message in a simpler format that might work better
            message = {
                "type": "sensor_data",
                "topic": "hackathon",
                "data": {
                    "roll": roll,
                    "pitch": pitch,
                    "x": x,
                    "y": y,
                    "z": z,
                    "timestamp": time.time(),
                    "device_id": "controller_esp32"
                }
            }
            
            # Try different HTTP methods and headers
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'ESP32-Controller'
            }
            
            print(f"Sending: Roll={roll:.1f}°, Pitch={pitch:.1f}°")
            
            # Try PUT instead of POST
            response = requests.put(
                CHANNEL_URL, 
                data=ujson.dumps(message), 
                headers=headers,
                timeout=10
            )
            
            success = response.status_code in [200, 201, 202]
            
            if success:
                print(f"✓ Data sent successfully (HTTP {response.status_code})")
            else:
                print(f"✗ HTTP Error: {response.status_code}")
                try:
                    print(f"Response: {response.text[:200]}")
                except:
                    pass
            
            response.close()
            return success
            
        except Exception as e:
            print(f"Send error: {e}")
            return False
    
    def run(self):
        """Main loop"""
        print("Controller running - sending accelerometer data...")
        print("Press Ctrl+C to stop")
        
        # Check connections
        wlan = network.WLAN(network.STA_IF)
        
        try:
            while True:
                current_time = time.ticks_ms()
                sensor_data = {}
                send_success = False
                
                # Read and display sensor data
                if self.sensor_system:
                    try:
                        x, y, z = self.sensor_system.readaccel()
                        roll, pitch = self.sensor_system.readroll()
                        sensor_data = {
                            'roll': roll,
                            'pitch': pitch,
                            'x': x, 'y': y, 'z': z
                        }
                        print(f"Sensors: Roll={roll:.1f}°, Pitch={pitch:.1f}° | Raw: X={x}, Y={y}, Z={z}")
                    except Exception as e:
                        print(f"Sensor read error: {e}")
                
                # Send data if WiFi is connected
                if wlan.isconnected() and time.ticks_diff(current_time, self.last_send) > self.send_interval:
                    send_success = self.send_data_websocket_style()
                    sensor_data['sent'] = send_success
                    self.last_send = current_time
                
                # Update display
                if time.ticks_diff(current_time, self.last_display_update) > self.display_update_interval:
                    wifi_status = "Connected" if wlan.isconnected() else "Disconnected"
                    status = "Sending" if sensor_data else "No Sensors"
                    self.update_display(status, wifi_status, sensor_data if sensor_data else None)
                    self.last_display_update = current_time
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\nController stopped by user")
            if self.display:
                self.display.fill(0)
                self.display.text("STOPPED", 35, 30)
                self.display.show()
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(2)

# Auto-run when uploaded to ESP32
if __name__ == "__main__":
    print("="*60)
    print("ESP32 SMART MOTOR CONTROLLER - Fixed Version")
    print("SETUP REQUIRED:")
    print("1. Set SSID and PASSWORD for your WiFi")
    print("2. Upload sensors.py and adxl345.py to ESP32")
    print("3. Connect ADXL345 accelerometer to I2C pins")
    print("4. Connect OLED display to I2C (SCL=22, SDA=21)")
    print("5. Save this file as 'main.py' to auto-run on boot")
    print("="*60)
    
    controller = SmartMotorController()
    controller.run()
