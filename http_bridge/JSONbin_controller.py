"""
ESP32 SmartMotor Controller - OPTIMIZED JSONBin.io Version
High-speed potentiometer data transmission with minimal latency
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
JSONBIN_WRITE_URL = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}"

# Hardware configuration
POTENTIOMETER_PIN = 3
DISPLAY_AVAILABLE = True

# OPTIMIZED Communication settings
SEND_INTERVAL_MS = 300          # Reduced from 1000ms - much faster response
ANGLE_CHANGE_THRESHOLD = 1      # Reduced from 3 - more sensitive
HTTP_TIMEOUT = 3                # Reduced from 10 - faster failure detection
GC_FREQUENCY = 5                # More frequent garbage collection

class OptimizedSmartMotorController:
    def __init__(self):
        self.last_angle_sent = 90
        self.last_send_time = 0
        self.send_count = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.last_successful_send = time.ticks_ms()
        
        # Initialize hardware with fewer samples for speed
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
        
        print("OPTIMIZED SmartMotor Controller initialized")
        
    def connect_wifi(self):
        """Connect to WiFi network with faster timeout"""
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if wlan.isconnected():
            print(f"Already connected to WiFi. IP: {wlan.ifconfig()[0]}")
            return True
        
        print(f"Connecting to WiFi: {WIFI_SSID}")
        self.update_display_fast("Connecting", "WiFi...", "", "")
        
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        
        # Reduced timeout for faster startup
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
    
    def read_potentiometer_fast(self):
        """Optimized potentiometer reading with minimal samples"""
        try:
            # Take only 2 readings instead of 3 for speed
            reading1 = self.potentiometer.read()
            time.sleep_ms(1)  # Minimal delay
            reading2 = self.potentiometer.read()
            
            # Quick average
            avg_reading = (reading1 + reading2) // 2
            
            # Convert to angle
            angle = int((180.0 / 4095.0) * avg_reading)
            angle = max(0, min(180, angle))
            return angle
        except Exception as e:
            print(f"Potentiometer error: {e}")
            return self.last_angle_sent
    
    def send_data_optimized(self, angle):
        """OPTIMIZED: Single PUT request with minimal data"""
        try:
            # SIMPLIFIED data structure - only essential data
            data = {
                "angle": angle,        # Just the angle - no extra fields
                "count": self.send_count + 1,
                "time": time.ticks_ms()
            }
            
            headers = {
                "Content-Type": "application/json",
                "X-Master-Key": JSONBIN_API_KEY,
                "Connection": "close"  # Hint for connection reuse
            }
            
            # Single PUT request - no GET first!
            response = urequests.put(
                JSONBIN_WRITE_URL, 
                json=data, 
                headers=headers, 
                timeout=HTTP_TIMEOUT  # Much faster timeout
            )
            
            if response.status_code == 200:
                self.send_count += 1
                self.consecutive_errors = 0
                self.last_successful_send = time.ticks_ms()
                print(f"✅ Sent: {angle}° (#{self.send_count})")
                response.close()
                return True
            else:
                print(f"❌ HTTP error: {response.status_code}")
                response.close()
                self.consecutive_errors += 1
                return False
                
        except Exception as e:
            self.error_count += 1
            self.consecutive_errors += 1
            print(f"❌ Send error: {e}")
            return False
    
    def update_display_fast(self, line1="", line2="", line3="", line4=""):
        """Optimized display update - only when needed"""
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
            pass  # Fail silently to maintain speed
    
    def is_connection_healthy(self):
        """Check if connection is still responsive"""
        time_since_success = time.ticks_diff(time.ticks_ms(), self.last_successful_send)
        return self.consecutive_errors < 5 and time_since_success < 10000  # 10 second health check
    
    def run(self):
        """OPTIMIZED main control loop"""
        print("Starting OPTIMIZED SmartMotor Controller...")
        
        # Connect to WiFi
        if not self.connect_wifi():
            print("Failed to connect to WiFi. Exiting.")
            return
        
        print(f"🚀 OPTIMIZED Controller Running:")
        print(f"   📡 Send Interval: {SEND_INTERVAL_MS}ms")
        print(f"   🎯 Sensitivity: {ANGLE_CHANGE_THRESHOLD}°")
        print(f"   ⏱️  Timeout: {HTTP_TIMEOUT}s")
        print(f"   📊 Bin ID: {JSONBIN_BIN_ID}")
        
        # Main loop - OPTIMIZED
        while True:
            try:
                current_time = time.ticks_ms()
                
                # Check if it's time to send (much more frequent)
                if time.ticks_diff(current_time, self.last_send_time) >= SEND_INTERVAL_MS:
                    
                    # Fast potentiometer read
                    angle = self.read_potentiometer_fast()
                    
                    # More sensitive change detection
                    angle_change = abs(angle - self.last_angle_sent)
                    
                    if angle_change >= ANGLE_CHANGE_THRESHOLD or self.send_count == 0:
                        # Send data with optimized method
                        if self.send_data_optimized(angle):
                            self.last_angle_sent = angle
                            self.last_send_time = current_time
                            
                            # Update display with success
                            self.update_display_fast(
                                "CONTROLLER",
                                f"Sent: {angle}°",
                                f"Rate: {SEND_INTERVAL_MS}ms",
                                f"#{self.send_count} E:{self.error_count}"
                            )
                        else:
                            # Display error but keep trying
                            self.update_display_fast(
                                "CONTROLLER",
                                f"Angle: {angle}°",
                                "SEND FAILED",
                                f"#{self.send_count} E:{self.error_count}"
                            )
                    else:
                        # Update display showing current reading
                        self.update_display_fast(
                            "CONTROLLER", 
                            f"Angle: {angle}°",
                            f"Last: {self.last_angle_sent}°",
                            f"#{self.send_count} E:{self.error_count}"
                        )
                    
                    # Reset timer regardless of send result
                    self.last_send_time = current_time
                
                # Optimized garbage collection
                if self.send_count % GC_FREQUENCY == 0:
                    gc.collect()
                
                # Check connection health
                if not self.is_connection_healthy():
                    print("⚠️ Connection health poor, continuing...")
                    self.consecutive_errors = 0  # Reset and keep trying
                
                # Minimal loop delay for maximum responsiveness
                time.sleep_ms(50)
                
            except KeyboardInterrupt:
                print("Shutting down...")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.error_count += 1
                time.sleep(1)  # Brief pause on major errors

# Run the optimized controller
if __name__ == "__main__":
    controller = OptimizedSmartMotorController()
    controller.run()
