"""
ESP32 SmartMotor Receiver - HTTP Bridge Version
Polls bridge server for data and controls servo motor
"""

import network
import urequests
import json
import time
import gc
from machine import Pin, PWM

# Configuration - Update these for your setup
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""
BRIDGE_SERVER_IP = ""  # Update to your bridge server IP
BRIDGE_PORT = 8080

# Hardware configuration
SERVO_PIN = 2
DISPLAY_AVAILABLE = True  # Set to False if no display

# Communication settings
POLL_INTERVAL_MS = 200  # Poll bridge server every 200ms (5 times per second)
WIFI_TIMEOUT = 30  # WiFi connection timeout in seconds

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
        self.wlan = None
        self.current_servo_angle = 90
        self.poll_count = 0
        self.error_count = 0
        self.last_poll_time = 0
        
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
        
        print("SmartMotor Receiver initialized")
        
    def connect_wifi(self):
        """Connect to WiFi network"""
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        
        if self.wlan.isconnected():
            print(f"Already connected to WiFi. IP: {self.wlan.ifconfig()[0]}")
            return True
        
        print(f"Connecting to WiFi: {WIFI_SSID}")
        self.update_display("Connecting", "to WiFi...", "", "")
        
        self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        # Wait for connection
        timeout = WIFI_TIMEOUT
        while not self.wlan.isconnected() and timeout > 0:
            print(".", end="")
            time.sleep(1)
            timeout -= 1
            
            if timeout % 5 == 0:
                self.update_display("Connecting", f"WiFi {timeout}s", "", "")
        
        if self.wlan.isconnected():
            ip = self.wlan.ifconfig()[0]
            print(f"\nWiFi connected! IP: {ip}")
            self.update_display("WiFi Connected", ip, "", "")
            time.sleep(2)
            return True
        else:
            print("\nWiFi connection failed!")
            self.update_display("WiFi Failed", "Check config", "", "")
            return False
    
    def poll_bridge_server(self):
        """Poll bridge server for new angle data"""
        try:
            url = f"http://{BRIDGE_SERVER_IP}:{BRIDGE_PORT}/api/receiver"
            
            # Send HTTP GET request
            response = urequests.get(url, timeout=2)
            
            if response.status_code == 200:
                data = response.json()
                angle = data.get('angle', 90)
                age_seconds = data.get('age_seconds', 0)
                
                self.poll_count += 1
                response.close()
                
                # Only move servo if data is recent
                if age_seconds < 2.0:  # Data less than 2 seconds old
                    return angle
                else:
                    print(f"Data too old: {age_seconds:.1f}s")
                    return None
            else:
                print(f"Bridge server error: {response.status_code}")
                response.close()
                return None
                
        except Exception as e:
            self.error_count += 1
            print(f"Poll error: {e}")
            return None
    
    def move_servo(self, angle):
        """Move servo to specified angle"""
        try:
            angle = max(0, min(180, int(angle)))
            self.servo.write_angle(angle)
            self.current_servo_angle = angle
            print(f"Moved servo to: {angle}°")
            return True
        except Exception as e:
            print(f"Servo error: {e}")
            return False
    
    def send_confirmation_to_bridge(self, angle):
        """Send servo position confirmation back to bridge"""
        try:
            url = f"http://{BRIDGE_SERVER_IP}:{BRIDGE_PORT}/api/receiver"
            data = {"angle": angle}
            
            # Send HTTP POST request
            response = urequests.post(url, json=data, timeout=1)
            
            if response.status_code == 200:
                print(f"Confirmed: {angle}°")
                response.close()
                return True
            else:
                response.close()
                return False
                
        except Exception as e:
            print(f"Confirmation error: {e}")
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
        print("Starting SmartMotor Receiver...")
        
        # Connect to WiFi
        if not self.connect_wifi():
            print("Failed to connect to WiFi. Exiting.")
            return
        
        print(f"Bridge server: {BRIDGE_SERVER_IP}:{BRIDGE_PORT}")
        print("Starting data polling...")
        
        # Main loop
        while True:
            try:
                current_time = time.ticks_ms()
                
                # Check if it's time to poll
                if time.ticks_diff(current_time, self.last_poll_time) >= POLL_INTERVAL_MS:
                    # Poll bridge server for new data
                    new_angle = self.poll_bridge_server()
                    
                    if new_angle is not None:
                        # Check if angle changed
                        angle_change = abs(new_angle - self.current_servo_angle)
                        
                        if angle_change >= 1:  # Move on any change >= 1 degree
                            if self.move_servo(new_angle):
                                # Send confirmation back to bridge
                                self.send_confirmation_to_bridge(new_angle)
                                
                                # Update display
                                self.update_display(
                                    "RECEIVER",
                                    f"Servo: {new_angle}°",
                                    f"Polls: #{self.poll_count}",
                                    f"Errors: {self.error_count}"
                                )
                        else:
                            # Update display without moving
                            self.update_display(
                                "RECEIVER",
                                f"Servo: {self.current_servo_angle}°",
                                f"Target: {new_angle}°",
                                f"Polls: #{self.poll_count}"
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
                
                # Small delay to prevent overwhelming the system
                time.sleep_ms(50)
                
                # Periodic garbage collection
                if self.poll_count % 50 == 0:
                    gc.collect()
                
            except KeyboardInterrupt:
                print("Shutting down...")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.error_count += 1
                time.sleep(1)

# Run the receiver
if __name__ == "__main__":
    receiver = SmartMotorReceiver()
    receiver.run()
