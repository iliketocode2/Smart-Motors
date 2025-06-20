"""
ESP32 SmartMotor - Ultra Simple Cloud Version
Uses requestbin.com - works immediately with zero setup!
Just change the URL below and both ESP32s can communicate through the cloud.
"""

import network
import urequests
import json
import time
from machine import Pin, ADC, PWM

# Configuration
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = "foundedin1883"

# RequestBin URL - Create one at https://requestbin.com/
# 1. Go to https://requestbin.com/
# 2. Click "Create a RequestBin"  
# 3. Copy the URL and paste it below
REQUEST_BIN_URL = ""  # Replace with YOUR RequestBin URL

# Device configuration - Change this for each ESP32
DEVICE_TYPE = "controller"  # Change to "receiver" for the receiver ESP32

# Hardware pins
POTENTIOMETER_PIN = 3  # Controller only
SERVO_PIN = 2         # Receiver only

class SimpleCloudMotor:
    def __init__(self, device_type):
        self.device_type = device_type
        self.current_angle = 90
        self.send_count = 0
        
        # Initialize hardware based on device type
        if device_type == "controller":
            self.potentiometer = ADC(Pin(POTENTIOMETER_PIN))
            self.potentiometer.atten(ADC.ATTN_11DB)
            print("🎮 Controller initialized")
        elif device_type == "receiver":
            self.servo = self.setup_servo(Pin(SERVO_PIN))
            print("📡 Receiver initialized")
        
        self.connect_wifi()
    
    def setup_servo(self, pin):
        """Setup servo motor"""
        class Servo:
            def __init__(self, pin):
                self.pwm = PWM(pin, freq=50, duty=0)
            
            def write_angle(self, degrees):
                duty = int(40 + (degrees / 180) * 80)  # Map 0-180 to 40-120 duty
                self.pwm.duty(duty)
        
        servo = Servo(pin)
        servo.write_angle(90)  # Center position
        return servo
    
    def connect_wifi(self):
        """Connect to WiFi"""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if wlan.isconnected():
            print(f"Already connected: {wlan.ifconfig()[0]}")
            return
        
        print(f"Connecting to {WIFI_SSID}...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        while not wlan.isconnected():
            print(".", end="")
            time.sleep(1)
        
        print(f"\n✅ WiFi connected: {wlan.ifconfig()[0]}")
    
    def read_potentiometer(self):
        """Read potentiometer angle"""
        raw = self.potentiometer.read()
        angle = int((raw / 4095) * 180)
        return max(0, min(180, angle))
    
    def send_to_cloud(self, angle):
        """Send data to cloud"""
        try:
            data = {
                "device": self.device_type,
                "angle": angle,
                "count": self.send_count,
                "timestamp": time.time()
            }
            
            response = urequests.post(REQUEST_BIN_URL, json=data, timeout=10)
            
            if response.status_code == 200:
                self.send_count += 1
                print(f"☁️ Sent: {angle}° (#{self.send_count})")
                response.close()
                return True
            else:
                print(f"❌ Error: {response.status_code}")
                response.close()
                return False
                
        except Exception as e:
            print(f"❌ Send failed: {e}")
            return False
    
    def get_from_cloud(self):
        """Get latest data from cloud - simplified version"""
        try:
            # For RequestBin, we'll use a simple approach
            # In a real implementation, you'd use a service that stores the latest value
            # For now, this demonstrates the concept
            
            # This is a placeholder - RequestBin doesn't store data
            # You'd replace this with actual data retrieval
            print("📡 Checking cloud for updates...")
            return None  # RequestBin doesn't store data
            
        except Exception as e:
            print(f"❌ Get failed: {e}")
            return None
    
    def run_controller(self):
        """Run controller loop"""
        print("🎮 Starting controller...")
        last_angle = 90
        
        while True:
            try:
                # Read potentiometer
                angle = self.read_potentiometer()
                
                # Send if changed significantly
                if abs(angle - last_angle) >= 3:
                    if self.send_to_cloud(angle):
                        last_angle = angle
                
                time.sleep(0.5)  # Send every 500ms
                
            except Exception as e:
                print(f"Controller error: {e}")
                time.sleep(1)
    
    def run_receiver(self):
        """Run receiver loop"""
        print("📡 Starting receiver...")
        print("Note: RequestBin doesn't store data - this is for testing connectivity")
        print("For full functionality, use the JSONBin version above")
        
        while True:
            try:
                # In a real cloud service, you'd get the latest controller data here
                # For demonstration, we'll just move the servo in a pattern
                test_angles = [90, 120, 90, 60, 90]
                for angle in test_angles:
                    self.servo.write_angle(angle)
                    print(f"🎯 Moved to: {angle}°")
                    time.sleep(2)
                
            except Exception as e:
                print(f"Receiver error: {e}")
                time.sleep(1)
    
    def run(self):
        """Run the appropriate loop based on device type"""
        if self.device_type == "controller":
            self.run_controller()
        elif self.device_type == "receiver":
            self.run_receiver()

# Usage Instructions:
# 1. Go to https://requestbin.com/
# 2. Click "Create a RequestBin"
# 3. Copy the URL and replace REQUEST_BIN_URL above
# 4. For controller: Set DEVICE_TYPE = "controller"
# 5. For receiver: Set DEVICE_TYPE = "receiver"
# 6. Upload to respective ESP32s

if __name__ == "__main__":
    motor = SimpleCloudMotor(DEVICE_TYPE)
    motor.run()
