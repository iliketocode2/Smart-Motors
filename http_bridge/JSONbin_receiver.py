"""
ESP32 SmartMotor Receiver - ULTRA-HIGH-SPEED JSONBin.io Version  
Maximum speed servo control with ultra-low latency polling
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
JSONBIN_BIN_ID = ""  # Same as controller
JSONBIN_API_KEY = ""  # Same as controller

# Hardware configuration
SERVO_PIN = 2
DISPLAY_AVAILABLE = True

# ULTRA-HIGH-SPEED Communication settings
POLL_INTERVAL_MS = 100
HTTP_TIMEOUT = 1
SERVO_MOVE_THRESHOLD = 1
GC_FREQUENCY = 15               # Less frequent GC for speed
LOOP_DELAY_MS = 5

class UltraFastServo:
    """Ultra-optimized servo with minimal overhead"""
    def __init__(self, pin, freq=50, min_us=600, max_us=2400, angle=180):
        self.min_us = min_us
        self.max_us = max_us
        self.freq = freq
        self.angle = angle
        self.pwm = PWM(pin, freq=freq, duty=0)
        self.current_angle = 90

    def write_angle_ultra_fast(self, degrees):
        """Ultra-fast servo movement - no redundant checks"""
        try:
            if degrees == self.current_angle:
                return True  # Skip if same angle
            
            degrees = max(0, min(self.angle, int(degrees)))
            
            # Direct calculation for speed
            us = self.min_us + (self.max_us - self.min_us) * degrees / self.angle
            duty = int(us * 1024 * self.freq / 1000000)
            self.pwm.duty(duty)
            
            self.current_angle = degrees
            return True
        except:
            return False

class UltraFastSmartMotorReceiver:
    def __init__(self):
        self.current_servo_angle = 90
        self.poll_count = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.last_poll_time = 0
        self.last_successful_poll = time.ticks_ms()
        
        # Ultra-fast servo setup
        self.servo = UltraFastServo(Pin(SERVO_PIN))
        self.servo.write_angle_ultra_fast(90)
        print("Ultra-fast servo initialized")
        
        # Simplified display setup
        if DISPLAY_AVAILABLE:
            try:
                from machine import SoftI2C
                import ssd1306
                i2c = SoftI2C(scl=Pin(7), sda=Pin(6))
                self.display = ssd1306.SSD1306_I2C(128, 64, i2c)
                self.display_available = True
            except:
                self.display_available = False
        else:
            self.display_available = False
        
        print("🚀 ULTRA-FAST SmartMotor Receiver initialized")
        
    def connect_wifi(self):
        """Ultra-fast WiFi connection"""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if wlan.isconnected():
            print(f"WiFi OK: {wlan.ifconfig()[0]}")
            return True
        
        print(f"WiFi: {WIFI_SSID}")
        self.update_display_fast("WiFi...", "", "", "")
        
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        # Fast connection timeout
        timeout = 15
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
        
        if wlan.isconnected():
            print(f"WiFi connected: {wlan.ifconfig()[0]}")
            self.update_display_fast("WiFi OK", "Ready!", "", "")
            time.sleep(0.5)  # Minimal delay
            return True
        else:
            print("WiFi failed!")
            self.update_display_fast("WiFi FAIL", "", "", "")
            return False
    
    def poll_data_ultra_fast(self):
        """ULTRA-FAST: Minimal processing, maximum speed"""
        try:
            url = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}/latest"
            headers = {
                "X-Master-Key": JSONBIN_API_KEY
            }
            
            # Ultra-fast HTTP request
            response = urequests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                record = data.get("record", {})
                
                # Get angle from ultra-simplified structure
                angle = record.get("a", 90)  # Match controller's "a" key
                
                self.poll_count += 1
                self.consecutive_errors = 0
                self.last_successful_poll = time.ticks_ms()
                
                print(f"📡 {angle}° #{self.poll_count}")
                response.close()
                return angle
            else:
                self.consecutive_errors += 1
                response.close()
                return None
                
        except Exception as e:
            self.error_count += 1
            self.consecutive_errors += 1
            print(f"❌ {e}")
            return None
    
    def move_servo_ultra_fast(self, target_angle):
        """ULTRA-FAST: Immediate servo movement"""
        try:
            target_angle = max(0, min(180, int(target_angle)))
            
            # Move on any change for maximum responsiveness
            if target_angle != self.current_servo_angle:
                if self.servo.write_angle_ultra_fast(target_angle):
                    self.current_servo_angle = target_angle
                    print(f"🎯 {target_angle}°")
                    return True
            return True  # No movement needed
                
        except Exception as e:
            print(f"❌ Servo: {e}")
            return False
    
    def update_display_fast(self, line1="", line2="", line3="", line4=""):
        """Ultra-fast display with minimal processing"""
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
            pass
    
    def run(self):
        """ULTRA-HIGH-SPEED main loop"""
        print("🚀 ULTRA-FAST Receiver Starting...")
        
        if not self.connect_wifi():
            print("WiFi failed. Exiting.")
            return
        
        print(f"⚡ ULTRA-FAST MODE:")
        print(f"   📡 Poll every {POLL_INTERVAL_MS}ms")
        print(f"   🎯 Move on any change")
        print(f"   ⚡ Timeout: {HTTP_TIMEOUT}s")
        print("   🔥 MAXIMUM SPEED MODE ACTIVE!")
        
        # ULTRA-HIGH-SPEED main loop
        while True:
            try:
                current_time = time.ticks_ms()
                
                # Ultra-frequent polling check
                if time.ticks_diff(current_time, self.last_poll_time) >= POLL_INTERVAL_MS:
                    
                    # Ultra-fast data poll
                    new_angle = self.poll_data_ultra_fast()
                    
                    if new_angle is not None:
                        # Try ultra-fast servo movement
                        if self.move_servo_ultra_fast(new_angle):
                            # Success display
                            rate = 1000 / POLL_INTERVAL_MS  # Calculate Hz
                            self.update_display_fast(
                                "ULTRA-RECV",
                                f"Servo: {self.current_servo_angle}°",
                                f"{rate:.1f}Hz #{self.poll_count}",
                                f"Errors: {self.error_count}"
                            )
                        else:
                            # Servo error display
                            self.update_display_fast(
                                "ULTRA-RECV",
                                f"Target: {new_angle}°",
                                "SERVO FAIL",
                                f"#{self.poll_count} E:{self.error_count}"
                            )
                    else:
                        # Poll error display
                        self.update_display_fast(
                            "ULTRA-RECV",
                            f"Servo: {self.current_servo_angle}°",
                            "POLL FAIL",
                            f"#{self.poll_count} E:{self.error_count}"
                        )
                    
                    self.last_poll_time = current_time
                
                # Ultra-efficient garbage collection
                if self.poll_count % GC_FREQUENCY == 0 and self.poll_count > 0:
                    gc.collect()
                
                # Reset consecutive errors periodically
                if self.consecutive_errors > 3:
                    print("⚠️ Multiple errors, continuing...")
                    self.consecutive_errors = 0
                
                # MINIMAL delay for MAXIMUM responsiveness
                time.sleep_ms(LOOP_DELAY_MS)
                
            except KeyboardInterrupt:
                print("Shutting down ultra-fast receiver...")
                # Return servo to center on shutdown
                self.servo.write_angle_ultra_fast(90)
                break
            except Exception as e:
                print(f"Main error: {e}")
                self.error_count += 1
                time.sleep_ms(100)

# Run the ultra-fast receiver
if __name__ == "__main__":
    print("🔥 ULTRA-HIGH-SPEED MODE LOADING...")
    receiver = UltraFastSmartMotorReceiver()
    receiver.run()
