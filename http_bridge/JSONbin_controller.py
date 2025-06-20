"""
ESP32 SmartMotor Controller - JSONBin.io Final Version
Sends potentiometer data to JSONBin.io cloud storage
"""

import network
import urequests
import json
import time
import gc
from machine import Pin, ADC

# WiFi Configuration
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""

# JSONBin.io Configuration - UPDATE THESE WITH YOUR VALUES
JSONBIN_BIN_ID = "YOUR_BIN_ID_HERE"        # Replace with your Bin ID
JSONBIN_API_KEY = "YOUR_API_KEY_HERE"      # Replace with your Master Key

# JSONBin.io URLs
JSONBIN_BASE_URL = "https://api.jsonbin.io/v3/b"
JSONBIN_READ_URL = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}/latest"
JSONBIN_WRITE_URL = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}"

# Hardware configuration
POTENTIOMETER_PIN = 3
DISPLAY_AVAILABLE = True

# Communication settings
SEND_INTERVAL_MS = 1000  # Send every 1 second (cloud services are slower)
ANGLE_CHANGE_THRESHOLD = 3  # Send when angle changes by 3+ degrees

class SmartMotorController:
    def __init__(self):
        self.last_angle_sent = 90
        self.last_send_time = 0
        self.send_count = 0
        self.error_count = 0
        self.last_receiver_angle = 90
        
        # Initialize hardware
        self.potentiometer = ADC(Pin(POTENTIOMETER_PIN))
        self.potentiometer.atten(ADC.ATTN_11DB)
        
        # Initialize display if available
        if DISPLAY_AVAILABLE:
            try:
                from machine import SoftI2C
                import ssd1306
                i2c = SoftI2C(scl=Pin(7), sda=Pin(6))
                self.display = ssd1306.SSD1306_I2C(128, 64, i2c)
                self.display_available = True
                print("Display initialized")
            except:
                self.display_available = False
                print("Display not available")
        else:
            self.display_available = False
        
        print("SmartMotor Controller initialized (JSONBin.io)")
        
    def connect_wifi(self):
        """Connect to WiFi network"""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if wlan.isconnected():
            print(f"Already connected to WiFi. IP: {wlan.ifconfig()[0]}")
            return True
        
        print(f"Connecting to WiFi: {WIFI_SSID}")
        self.update_display("Connecting", "to WiFi...", "", "")
        
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        # Wait for connection
        timeout = 30
        while not wlan.isconnected() and timeout > 0:
            print(".", end="")
            time.sleep(1)
            timeout -= 1
        
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"\nWiFi connected! IP: {ip}")
            self.update_display("WiFi Connected", "JSONBin Ready", "", "")
            time.sleep(2)
            return True
        else:
            print("\nWiFi connection failed!")
            self.update_display("WiFi Failed", "Check config", "", "")
            return False
    
    def read_potentiometer(self):
        """Read potentiometer value and convert to angle"""
        try:
            raw_value = self.potentiometer.read()
            angle = int((180.0 / 4095.0) * raw_value)
            angle = max(0, min(180, angle))
            return angle
        except Exception as e:
            print(f"Potentiometer read error: {e}")
            return self.last_angle_sent
    
    def get_current_data_from_jsonbin(self):
        """Get current data from JSONBin to preserve receiver data"""
        try:
            headers = {
                "X-Master-Key": JSONBIN_API_KEY
            }
            
            response = urequests.get(JSONBIN_READ_URL, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                record = data.get("record", {})
                self.last_receiver_angle = record.get("receiver_angle", 90)
                response.close()
                return record
            else:
                print(f"JSONBin read error: {response.status_code}")
                response.close()
                return None
                
        except Exception as e:
            print(f"JSONBin read error: {e}")
            return None
    
    def send_data_to_jsonbin(self, angle):
        """Send angle data to JSONBin.io"""
        try:
            # First get current data to preserve receiver info
            current_data = self.get_current_data_from_jsonbin()
            
            # Create updated data
            data = {
                "controller_angle": angle,
                "receiver_angle": self.last_receiver_angle,
                "controller_count": self.send_count + 1,
                "receiver_count": current_data.get("receiver_count", 0) if current_data else 0,
                "last_update": time.time()
            }
            
            headers = {
                "Content-Type": "application/json",
                "X-Master-Key": JSONBIN_API_KEY
            }
            
            response = urequests.put(JSONBIN_WRITE_URL, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                self.send_count += 1
                print(f"✅ Sent to JSONBin: {angle}° (#{self.send_count})")
                response.close()
                return True
            else:
                print(f"❌ JSONBin error: {response.status_code}")
                response.close()
                return False
                
        except Exception as e:
            self.error_count += 1
            print(f"❌ Send error: {e}")
            return False
    
    def update_display(self, line1="", line2="", line3="", line4=""):
        """Update OLED display if available"""
        if not self.display_available:
            return
        
        try:
            self.display.fill(0)
            if line1:
                self.display.text(line1[:16], 0, 10)
            if line2:
                self.display.text(line2[:16], 0, 25)
            if line3:
                self.display.text(line3[:16], 0, 40)
            if line4:
                self.display.text(line4[:16], 0, 55)
            self.display.show()
        except Exception as e:
            print(f"Display error: {e}")
    
    def run(self):
        """Main control loop"""
        print("Starting SmartMotor Controller (JSONBin.io)...")
        
        # Connect to WiFi
        if not self.connect_wifi():
            print("Failed to connect to WiFi. Exiting.")
            return
        
        print("🌐 Connected to JSONBin.io cloud service")
        print(f"📊 Bin ID: {JSONBIN_BIN_ID}")
        print("Starting data transmission...")
        
        # Main loop
        while True:
            try:
                current_time = time.ticks_ms()
                
                # Check if it's time to send data
                if time.ticks_diff(current_time, self.last_send_time) >= SEND_INTERVAL_MS:
                    # Read potentiometer
                    angle = self.read_potentiometer()
                    
                    # Check if angle changed significantly
                    angle_change = abs(angle - self.last_angle_sent)
                    
                    if angle_change >= ANGLE_CHANGE_THRESHOLD:
                        # Send data to JSONBin
                        if self.send_data_to_jsonbin(angle):
                            self.last_angle_sent = angle
                            self.last_send_time = current_time
                            
                            # Update display
                            self.update_display(
                                "CONTROLLER",
                                f"Sent: {angle}°",
                                f"Recv: {self.last_receiver_angle}°",
                                f"Count: #{self.send_count}"
                            )
                        else:
                            # Update display with error
                            self.update_display(
                                "CONTROLLER",
                                f"Angle: {angle}°",
                                "Send Failed",
                                f"Errors: {self.error_count}"
                            )
                    else:
                        # Update display without sending
                        self.update_display(
                            "CONTROLLER",
                            f"Angle: {angle}°",
                            f"Last: {self.last_angle_sent}°",
                            f"Count: #{self.send_count}"
                        )
                
                # Small delay
                time.sleep_ms(100)
                
                # Periodic garbage collection
                if self.send_count % 10 == 0:
                    gc.collect()
                
            except KeyboardInterrupt:
                print("Shutting down...")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.error_count += 1
                time.sleep(2)

# Run the controller
if __name__ == "__main__":
    controller = SmartMotorController()
    controller.run()
