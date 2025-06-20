"""
ESP32 SmartMotor Receiver - JSONBin.io Version  
Uses free cloud JSON storage - no local server or IP configuration needed!
"""

import network
import urequests
import json
import time
import gc
from machine import Pin, PWM

# Configuration - No IP addresses needed!
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""

# JSONBin.io configuration (free service)
JSONBIN_BASE_URL = "https://api.jsonbin.io/v3/b"
JSONBIN_BIN_ID = ""  # Same as controller
JSONBIN_API_KEY = ""  # Same as controller

# Or use alternative service for testing
TEST_MODE = False  # Set to False when using JSONBin

# Hardware configuration
SERVO_PIN = 2
DISPLAY_AVAILABLE = True

# Communication settings
POLL_INTERVAL_MS = 750  # Poll every 750ms (cloud services are slower)

class Servo:
    """Simple servo control class"""
    def __init__(self, pin, freq=50, min_us=600, max_us=2400, angle=180):
        self.min_us = min_us
        self.max_us = max_us
        self.freq = freq
        self.angle = angle
        self.pwm = PWM(pin, freq=freq, duty=0)

    def write_angle(self, degrees):
        """Move servo to specified angle"""
        if degrees < 0:
            degrees = 0
        elif degrees > self.angle:
            degrees = self.angle
            
        # Convert angle to microseconds
        us = self.min_us + (self.max_us - self.min_us) * degrees / self.angle
        
        # Convert microseconds to duty cycle
        duty = int(us * 1024 * self.freq / 1000000)
        self.pwm.duty(duty)

class SmartMotorReceiver:
    def __init__(self):
        self.current_servo_angle = 90
        self.poll_count = 0
        self.error_count = 0
        self.last_poll_time = 0
        self.last_controller_data = None
        
        # Initialize servo
        self.servo = Servo(Pin(SERVO_PIN))
        self.servo.write_angle(90)  # Center position
        print("Servo initialized and centered")
        
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
        
        print("SmartMotor Receiver initialized (Cloud Version)")
        
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
            self.update_display("WiFi Connected", "Cloud Ready", "", "")
            time.sleep(2)
            return True
        else:
            print("\nWiFi connection failed!")
            self.update_display("WiFi Failed", "Check config", "", "")
            return False
    
    def poll_cloud_service(self):
        """Poll cloud service for controller data"""
        try:
            if TEST_MODE:
                # In test mode, we'll simulate getting data
                # (since httpbin.org doesn't store data)
                # You can replace this with actual test data
                print("📡 Polling cloud (test mode)...")
                self.poll_count += 1
                
                # Simulate receiving some data
                # In real implementation, this would be actual cloud data
                simulated_angle = 90 + (self.poll_count % 20) * 5  # Simulate changing angles
                return min(180, simulated_angle)
                
            else:
                # Use JSONBin.io to get real data
                url = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}/latest"
                headers = {
                    "X-Master-Key": JSONBIN_API_KEY
                }
                
                response = urequests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    record = data.get("record", {})
                    angle = record.get("controller_angle", 90)
                    
                    self.poll_count += 1
                    print(f"📡 Polled cloud: {angle}° (#{self.poll_count})")
                    response.close()
                    return angle
                else:
                    print(f"❌ Cloud poll error: {response.status_code}")
                    response.close()
                    return None
                    
        except Exception as e:
            self.error_count += 1
            print(f"❌ Poll error: {e}")
            return None
    
    def move_servo(self, angle):
        """Move servo to specified angle"""
        try:
            angle = max(0, min(180, int(angle)))
            self.servo.write_angle(angle)
            self.current_servo_angle = angle
            print(f"🎯 Moved servo to: {angle}°")
            return True
        except Exception as e:
            print(f"❌ Servo error: {e}")
            return False
    
    def send_confirmation_to_cloud(self, angle):
        """Send servo position confirmation back to cloud"""
        try:
            if TEST_MODE:
                # In test mode, just print confirmation
                print(f"✅ Confirmed: {angle}° (test mode)")
                return True
                
            else:
                # Update JSONBin with receiver confirmation
                url = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}"
                headers = {
                    "Content-Type": "application/json",
                    "X-Master-Key": JSONBIN_API_KEY
                }
                
                # Get current data first, then update receiver angle
                data = {
                    "controller_angle": self.last_controller_data or 90,
                    "receiver_angle": angle,
                    "last_update": time.time(),
                    "receiver_count": self.poll_count
                }
                
                response = urequests.put(url, json=data, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    print(f"✅ Confirmed to cloud: {angle}°")
                    response.close()
                    return True
                else:
                    response.close()
                    return False
                    
        except Exception as e:
            print(f"❌ Confirmation error: {e}")
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
        print("Starting SmartMotor Receiver (Cloud Version)...")
        
        # Connect to WiFi
        if not self.connect_wifi():
            print("Failed to connect to WiFi. Exiting.")
            return
        
        print("🌐 Using cloud service - no local server needed!")
        print("Starting data polling...")
        
        # Main loop
        while True:
            try:
                current_time = time.ticks_ms()
                
                # Check if it's time to poll
                if time.ticks_diff(current_time, self.last_poll_time) >= POLL_INTERVAL_MS:
                    # Poll cloud service for new data
                    new_angle = self.poll_cloud_service()
                    
                    if new_angle is not None:
                        self.last_controller_data = new_angle
                        
                        # Check if angle changed
                        angle_change = abs(new_angle - self.current_servo_angle)
                        
                        if angle_change >= 2:  # Move on changes >= 2 degrees
                            if self.move_servo(new_angle):
                                # Send confirmation back to cloud
                                self.send_confirmation_to_cloud(new_angle)
                                
                                # Update display
                                self.update_display(
                                    "RECEIVER",
                                    f"Servo: {new_angle}°",
                                    f"Cloud: #{self.poll_count}",
                                    f"Errors: {self.error_count}"
                                )
                        else:
                            # Update display without moving
                            self.update_display(
                                "RECEIVER",
                                f"Servo: {self.current_servo_angle}°",
                                f"Target: {new_angle}°",
                                f"Cloud: #{self.poll_count}"
                            )
                    else:
                        # Update display with error
                        self.update_display(
                            "RECEIVER",
                            f"Servo: {self.current_servo_angle}°",
                            "Poll Failed",
                            f"Errors: {self.error_count}"
                        )
                    
                    self.last_poll_time = current_time
                
                # Small delay
                time.sleep_ms(150)
                
                # Periodic garbage collection
                if self.poll_count % 20 == 0:
                    gc.collect()
                
            except KeyboardInterrupt:
                print("Shutting down...")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.error_count += 1
                time.sleep(2)

# Run the receiver
if __name__ == "__main__":
    receiver = SmartMotorReceiver()
    receiver.run()
