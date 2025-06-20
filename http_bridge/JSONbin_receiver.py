"""
ESP32 SmartMotor Receiver - OPTIMIZED JSONBin.io Version  
High-speed servo control with minimal latency polling
"""

import network
import urequests
import json
import time
import gc
from machine import Pin, PWM

# Configuration
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""

# JSONBin.io configuration - SAME AS CONTROLLER
JSONBIN_BASE_URL = "https://api.jsonbin.io/v3/b"
JSONBIN_BIN_ID = "YOUR_BIN_ID_HERE"  # Same as controller
JSONBIN_API_KEY = "YOUR_API_KEY_HERE"  # Same as controller

# Hardware configuration
SERVO_PIN = 2
DISPLAY_AVAILABLE = True

# OPTIMIZED Communication settings
POLL_INTERVAL_MS = 250          # Much faster - reduced from 750ms
HTTP_TIMEOUT = 3                # Faster timeout - reduced from 10s
SERVO_MOVE_THRESHOLD = 1        # Move on 1° change instead of 2°
GC_FREQUENCY = 8                # More frequent garbage collection

class OptimizedServo:
    """Optimized servo control with faster response"""
    def __init__(self, pin, freq=50, min_us=600, max_us=2400, angle=180):
        self.min_us = min_us
        self.max_us = max_us
        self.freq = freq
        self.angle = angle
        self.pwm = PWM(pin, freq=freq, duty=0)
        self.current_angle = 90

    def write_angle_fast(self, degrees):
        """Optimized servo movement with bounds checking"""
        try:
            degrees = max(0, min(self.angle, int(degrees)))
            
            # Skip if no change
            if degrees == self.current_angle:
                return True
            
            # Convert angle to microseconds
            us = self.min_us + (self.max_us - self.min_us) * degrees / self.angle
            
            # Convert to duty cycle
            duty = int(us * 1024 * self.freq / 1000000)
            self.pwm.duty(duty)
            
            self.current_angle = degrees
            return True
        except:
            return False

class OptimizedSmartMotorReceiver:
    def __init__(self):
        self.current_servo_angle = 90
        self.poll_count = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.last_poll_time = 0
        self.last_successful_poll = time.ticks_ms()
        self.last_angle_received = 90
        
        # Initialize optimized servo
        self.servo = OptimizedServo(Pin(SERVO_PIN))
        self.servo.write_angle_fast(90)  # Center position
        print("Optimized servo initialized")
        
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
        
        print("OPTIMIZED SmartMotor Receiver initialized")
        
    def connect_wifi(self):
        """Fast WiFi connection"""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if wlan.isconnected():
            print(f"Already connected to WiFi. IP: {wlan.ifconfig()[0]}")
            return True
        
        print(f"Connecting to WiFi: {WIFI_SSID}")
        self.update_display_fast("Connecting", "WiFi...", "", "")
        
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        # Faster connection timeout
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            print(".", end="")
            time.sleep(1)
            timeout -= 1
        
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"\nWiFi connected! IP: {ip}")
            self.update_display_fast("WiFi OK", "Ready!", "", "")
            time.sleep(1)
            return True
        else:
            print("\nWiFi connection failed!")
            self.update_display_fast("WiFi Failed", "Check config", "", "")
            return False
    
    def poll_data_optimized(self):
        """OPTIMIZED: Fast polling with simplified data structure"""
        try:
            url = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}/latest"
            headers = {
                "X-Master-Key": JSONBIN_API_KEY,
                "Connection": "close"  # Connection reuse hint
            }
            
            # Fast HTTP request with short timeout
            response = urequests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                record = data.get("record", {})
                
                # Get angle from simplified structure
                angle = record.get("angle", 90)  # Match controller's simplified format
                
                self.poll_count += 1
                self.consecutive_errors = 0
                self.last_successful_poll = time.ticks_ms()
                self.last_angle_received = angle
                
                print(f"📡 Polled: {angle}° (#{self.poll_count})")
                response.close()
                return angle
            else:
                print(f"❌ Poll error: {response.status_code}")
                response.close()
                self.consecutive_errors += 1
                return None
                
        except Exception as e:
            self.error_count += 1
            self.consecutive_errors += 1
            print(f"❌ Poll error: {e}")
            return None
    
    def move_servo_optimized(self, target_angle):
        """OPTIMIZED: Fast servo movement with minimal threshold"""
        try:
            target_angle = max(0, min(180, int(target_angle)))
            
            # More sensitive movement threshold
            angle_change = abs(target_angle - self.current_servo_angle)
            
            if angle_change >= SERVO_MOVE_THRESHOLD:
                if self.servo.write_angle_fast(target_angle):
                    self.current_servo_angle = target_angle
                    print(f"🎯 Moved: {self.current_servo_angle}°")
                    return True
            else:
                # Angle too close, no movement needed
                return True
                
        except Exception as e:
            print(f"❌ Servo error: {e}")
            return False
    
    def update_display_fast(self, line1="", line2="", line3="", line4=""):
        """Fast display update with error suppression"""
        if not self.display_available:
            return
        
        try:
            self.display.fill(0)
            if line1: self.display.text(line1[:16], 0, 10)
            if line2: self.display.text(line2[:16], 0, 25)
            if line3: self.display.text(line3[:16], 0, 40)
            if line4: self.display.text(line4[:16], 0, 55)
            self.display.show()
        except:
            pass  # Fail silently for speed
    
    def is_connection_healthy(self):
        """Check polling health"""
        time_since_success = time.ticks_diff(time.ticks_ms(), self.last_successful_poll)
        return self.consecutive_errors < 5 and time_since_success < 8000  # 8 second health check
    
    def run(self):
        """OPTIMIZED main control loop"""
        print("Starting OPTIMIZED SmartMotor Receiver...")
        
        # Connect to WiFi
        if not self.connect_wifi():
            print("Failed to connect to WiFi. Exiting.")
            return
        
        print(f"🚀 OPTIMIZED Receiver Running:")
        print(f"   📡 Poll Interval: {POLL_INTERVAL_MS}ms")
        print(f"   🎯 Move Threshold: {SERVO_MOVE_THRESHOLD}°")
        print(f"   ⏱️  Timeout: {HTTP_TIMEOUT}s")
        print(f"   📊 Bin ID: {JSONBIN_BIN_ID}")
        
        # Main loop - OPTIMIZED for speed
        while True:
            try:
                current_time = time.ticks_ms()
                
                # Check if it's time to poll (much more frequent)
                if time.ticks_diff(current_time, self.last_poll_time) >= POLL_INTERVAL_MS:
                    
                    # Fast poll for new data
                    new_angle = self.poll_data_optimized()
                    
                    if new_angle is not None:
                        # Try to move servo with optimized method
                        if self.move_servo_optimized(new_angle):
                            # Update display with success
                            self.update_display_fast(
                                "RECEIVER",
                                f"Servo: {self.current_servo_angle}°",
                                f"Rate: {POLL_INTERVAL_MS}ms",
                                f"#{self.poll_count} E:{self.error_count}"
                            )
                        else:
                            # Servo movement failed
                            self.update_display_fast(
                                "RECEIVER",
                                f"Target: {new_angle}°",
                                "SERVO FAILED",
                                f"#{self.poll_count} E:{self.error_count}"
                            )
                    else:
                        # Poll failed, show error
                        self.update_display_fast(
                            "RECEIVER",
                            f"Servo: {self.current_servo_angle}°",
                            "POLL FAILED",
                            f"#{self.poll_count} E:{self.error_count}"
                        )
                    
                    # Reset poll timer regardless of result
                    self.last_poll_time = current_time
                
                # Optimized garbage collection
                if self.poll_count % GC_FREQUENCY == 0:
                    gc.collect()
                
                # Check connection health
                if not self.is_connection_healthy():
                    print("⚠️ Connection health poor, continuing...")
                    self.consecutive_errors = 0  # Reset and keep trying
                
                # Minimal delay for maximum responsiveness
                time.sleep_ms(30)
                
            except KeyboardInterrupt:
                print("Shutting down...")
                # Return servo to center on shutdown
                self.servo.write_angle_fast(90)
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.error_count += 1
                time.sleep(1)

# Run the optimized receiver
if __name__ == "__main__":
    receiver = OptimizedSmartMotorReceiver()
    receiver.run()
