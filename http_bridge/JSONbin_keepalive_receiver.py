"""
ESP32 SmartMotor Receiver - HTTP Keep-Alive Optimization
Uses connection reuse to reduce polling overhead
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

JSONBIN_BIN_ID = ""  # Same as controller
JSONBIN_API_KEY = ""  # Same as controller
JSONBIN_BASE_URL = "https://api.jsonbin.io/v3/b"
JSONBIN_READ_URL = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}/latest"

# Hardware
SERVO_PIN = 2
DISPLAY_AVAILABLE = True

# HTTP Keep-Alive optimized settings
POLL_INTERVAL_MS = 200               # Faster polling - was 750ms
HTTP_TIMEOUT = 1                     # Longer timeout for keep-alive
SERVO_MOVE_THRESHOLD = 1             # Move on 1° change
CONNECTION_REUSE_COUNT = 15          # Reuse connection for N requests

class HTTPKeepAliveServo:
    """Optimized servo control"""
    def __init__(self, pin, freq=50, min_us=600, max_us=2400, angle=180):
        self.min_us = min_us
        self.max_us = max_us
        self.freq = freq
        self.angle = angle
        self.pwm = PWM(pin, freq=freq, duty=0)
        self.current_angle = 90

    def write_angle(self, degrees):
        try:
            if degrees == self.current_angle:
                return True
            
            degrees = max(0, min(self.angle, int(degrees)))
            us = self.min_us + (self.max_us - self.min_us) * degrees / self.angle
            duty = int(us * 1024 * self.freq / 1000000)
            self.pwm.duty(duty)
            self.current_angle = degrees
            return True
        except:
            return False

class HTTPKeepAliveReceiver:
    def __init__(self):
        self.current_servo_angle = 90
        self.poll_count = 0
        self.error_count = 0
        self.last_poll_time = 0
        self.connection_reuse_counter = 0
        
        # HTTP Keep-Alive session management
        self.session_headers = {
            "X-Master-Key": JSONBIN_API_KEY,
            "Connection": "keep-alive",        # Keep TCP connection open
            "Cache-Control": "no-cache",       # Prevent caching delays
            "User-Agent": "ESP32-SmartMotor-Receiver"
        }
        
        # Performance tracking
        self.response_times = []
        
        # Hardware setup
        self.servo = HTTPKeepAliveServo(Pin(SERVO_PIN))
        self.servo.write_angle(90)
        
        # Display setup
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
        
        print("HTTP Keep-Alive Receiver initialized")
        
    def connect_wifi(self):
        """Connect to WiFi"""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if wlan.isconnected():
            print(f"WiFi connected: {wlan.ifconfig()[0]}")
            return True
        
        print(f"Connecting to WiFi: {WIFI_SSID}")
        self.update_display("WiFi...", "", "", "")
        
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
        
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"WiFi connected: {ip}")
            self.update_display("WiFi Connected", ip[:12], "", "")
            time.sleep(1)
            return True
        else:
            print("WiFi connection failed")
            self.update_display("WiFi Failed", "", "", "")
            return False
    
    def poll_data_with_keepalive(self):
        """Poll JSONBin with connection reuse optimization"""
        try:
            # Enhanced headers for keep-alive
            headers = self.session_headers.copy()
            
            # Manage connection reuse
            if self.connection_reuse_counter > 0:
                headers["Connection"] = "keep-alive"
            else:
                headers["Connection"] = "close"  # Force new connection periodically
            
            # Time the request
            start_time = time.ticks_ms()
            
            # Make HTTP request with keep-alive
            response = urequests.get(
                JSONBIN_READ_URL, 
                headers=headers, 
                timeout=HTTP_TIMEOUT
            )
            
            # Calculate actual response time
            response_time = time.ticks_diff(time.ticks_ms(), start_time)
            
            if response.status_code == 200:
                data = response.json()
                record = data.get("record", {})
                
                # Extract angle from simplified or complex structure
                angle = record.get("angle", record.get("a", 90))
                
                self.poll_count += 1
                self.connection_reuse_counter = (self.connection_reuse_counter + 1) % CONNECTION_REUSE_COUNT
                
                # Track response times
                self.response_times.append(response_time)
                if len(self.response_times) > 10:
                    self.response_times = self.response_times[-10:]
                
                print(f"📡 Polled {angle}° in {response_time}ms (#{self.poll_count})")
                response.close()
                return angle, response_time
            else:
                print(f"❌ Poll error {response.status_code}")
                response.close()
                return None, response_time
                
        except Exception as e:
            self.error_count += 1
            print(f"❌ Poll error: {e}")
            
            # Reset connection counter on error
            self.connection_reuse_counter = 0
            return None, 0
    
    def move_servo(self, target_angle):
        """Move servo with threshold checking"""
        try:
            target_angle = max(0, min(180, int(target_angle)))
            
            # Check if movement is needed
            angle_change = abs(target_angle - self.current_servo_angle)
            
            if angle_change >= SERVO_MOVE_THRESHOLD:
                if self.servo.write_angle(target_angle):
                    self.current_servo_angle = target_angle
                    print(f"🎯 Moved servo to {target_angle}°")
                    return True
            else:
                # No movement needed, but still successful
                return True
                
        except Exception as e:
            print(f"❌ Servo error: {e}")
            return False
    
    def update_display(self, line1="", line2="", line3="", line4=""):
        """Update display"""
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
        """Main control loop with keep-alive optimization"""
        print("Starting HTTP Keep-Alive Receiver...")
        
        if not self.connect_wifi():
            print("WiFi connection failed. Exiting.")
            return
        
        print(f"🔄 HTTP Keep-Alive Mode:")
        print(f"   📡 Poll interval: {POLL_INTERVAL_MS}ms")
        print(f"   🔗 Connection reuse: {CONNECTION_REUSE_COUNT} requests")
        print(f"   ⏱️  Timeout: {HTTP_TIMEOUT}s")
        print(f"   🎯 Move threshold: {SERVO_MOVE_THRESHOLD}°")
        
        while True:
            try:
                current_time = time.ticks_ms()
                
                if time.ticks_diff(current_time, self.last_poll_time) >= POLL_INTERVAL_MS:
                    # Poll for new data with keep-alive
                    new_angle, response_time = self.poll_data_with_keepalive()
                    
                    if new_angle is not None:
                        # Try to move servo
                        if self.move_servo(new_angle):
                            # Calculate average response time
                            avg_response = sum(self.response_times) / len(self.response_times) if self.response_times else 0
                            
                            # Success display with timing info
                            self.update_display(
                                "KEEP-ALIVE",
                                f"Servo: {self.current_servo_angle}°",
                                f"Avg: {avg_response:.0f}ms",
                                f"#{self.poll_count} E:{self.error_count}"
                            )
                        else:
                            # Servo movement failed
                            self.update_display(
                                "KEEP-ALIVE",
                                f"Target: {new_angle}°",
                                "SERVO FAILED",
                                f"#{self.poll_count} E:{self.error_count}"
                            )
                    else:
                        # Poll failed
                        avg_response = sum(self.response_times) / len(self.response_times) if self.response_times else 0
                        self.update_display(
                            "KEEP-ALIVE",
                            f"Servo: {self.current_servo_angle}°",
                            "POLL FAILED",
                            f"#{self.poll_count} E:{self.error_count}"
                        )
                    
                    self.last_poll_time = current_time
                
                # Garbage collection
                if self.poll_count % 15 == 0 and self.poll_count > 0:
                    gc.collect()
                
                time.sleep_ms(50)
                
            except KeyboardInterrupt:
                print("Shutting down...")
                print(f"Final stats: {self.poll_count} polls, {self.error_count} errors")
                if self.response_times:
                    print(f"Average response time: {sum(self.response_times)/len(self.response_times):.1f}ms")
                # Return servo to center
                self.servo.write_angle(90)
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.error_count += 1
                time.sleep(1)

if __name__ == "__main__":
    receiver = HTTPKeepAliveReceiver()
    receiver.run()
