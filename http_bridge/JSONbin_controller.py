"""
ESP32 SmartMotor Controller - 2 second connection max due to HTTP limit
Claude lied :(
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
JSONBIN_BIN_ID = ""        # Replace with your Bin ID
JSONBIN_API_KEY = ""      # Replace with your Master Key

# JSONBin.io URLs
JSONBIN_BASE_URL = "https://api.jsonbin.io/v3/b"
JSONBIN_WRITE_URL = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}"

# Hardware configuration
POTENTIOMETER_PIN = 3
DISPLAY_AVAILABLE = True

# ULTRA-HIGH-SPEED Communication settings
SEND_INTERVAL_MS = 100
HTTP_TIMEOUT = 1
ANGLE_CHANGE_THRESHOLD = 2
GC_FREQUENCY = 15              # Less frequent GC for speed
LOOP_DELAY_MS = 5

class UltraFastSmartMotorController:
    def __init__(self):
        self.last_angle_sent = 90
        self.last_send_time = 0
        self.send_count = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.last_successful_send = time.ticks_ms()
        
        # Ultra-fast hardware setup
        self.potentiometer = ADC(Pin(POTENTIOMETER_PIN))
        self.potentiometer.atten(ADC.ATTN_11DB)
        
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
        
        # Fast connection - 15 second timeout
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
    
    def read_potentiometer_ultra_fast(self):
        """ULTRA-FAST: Single reading with bounds check"""
        try:
            # Single reading for maximum speed
            raw_value = self.potentiometer.read()
            angle = int((180.0 / 4095.0) * raw_value)
            return max(0, min(180, angle))
        except:
            return self.last_angle_sent
    
    def send_data_ultra_fast(self, angle):
        """ULTRA-FAST: Minimal data, maximum speed"""
        try:
            # MINIMAL data structure for speed
            data = {"a": angle, "c": self.send_count + 1}  # Shorter keys
            
            headers = {
                "Content-Type": "application/json",
                "X-Master-Key": JSONBIN_API_KEY
            }
            
            # Ultra-fast PUT request
            response = urequests.put(JSONBIN_WRITE_URL, json=data, headers=headers, timeout=HTTP_TIMEOUT)
            
            if response.status_code == 200:
                self.send_count += 1
                self.consecutive_errors = 0
                self.last_successful_send = time.ticks_ms()
                print(f"✅ {angle}° #{self.send_count}")
                response.close()
                return True
            else:
                self.consecutive_errors += 1
                response.close()
                return False
                
        except Exception as e:
            self.error_count += 1
            self.consecutive_errors += 1
            print(f"❌ {e}")
            return False
    
    def update_display_fast(self, line1="", line2="", line3="", line4=""):
        """Ultra-fast display - minimal overhead"""
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
        
        if not self.connect_wifi():
            print("WiFi failed. Exiting.")
            return

        
        # ULTRA-HIGH-SPEED main loop
        while True:
            try:
                current_time = time.ticks_ms()
                
                # Ultra-frequent sending check
                if time.ticks_diff(current_time, self.last_send_time) >= SEND_INTERVAL_MS:
                    
                    # Ultra-fast potentiometer read
                    angle = self.read_potentiometer_ultra_fast()
                    
                    # Maximum sensitivity change detection
                    if abs(angle - self.last_angle_sent) >= ANGLE_CHANGE_THRESHOLD or self.send_count == 0:
                        
                        if self.send_data_ultra_fast(angle):
                            self.last_angle_sent = angle
                            
                            # Success display update
                            rate = 1000 / SEND_INTERVAL_MS  # Calculate Hz
                            self.update_display_fast(
                                "ULTRA-CTRL",
                                f"Sent: {angle}°",
                                f"{rate:.1f}Hz #{self.send_count}",
                                f"Errors: {self.error_count}"
                            )
                        else:
                            # Error display
                            self.update_display_fast(
                                "ULTRA-CTRL",
                                f"Angle: {angle}°",
                                "SEND FAILED",
                                f"#{self.send_count} E:{self.error_count}"
                            )
                    else:
                        # No change - minimal display update
                        self.update_display_fast(
                            "ULTRA-CTRL", 
                            f"Ready: {angle}°",
                            f"Last: {self.last_angle_sent}°",
                            f"#{self.send_count}"
                        )
                    
                    self.last_send_time = current_time
                
                # Ultra-efficient garbage collection
                if self.send_count % GC_FREQUENCY == 0 and self.send_count > 0:
                    gc.collect()
                
                # Reset consecutive errors periodically
                if self.consecutive_errors > 3:
                    print("⚠️ Multiple errors, continuing...")
                    self.consecutive_errors = 0
                
                # MINIMAL loop delay for MAXIMUM responsiveness
                time.sleep_ms(LOOP_DELAY_MS)
                
            except KeyboardInterrupt:
                print("Shutting down ultra-fast controller...")
                break
            except Exception as e:
                print(f"Main error: {e}")
                self.error_count += 1
                time.sleep_ms(100)

# Run the ultra-fast controller
if __name__ == "__main__":
    controller = UltraFastSmartMotorController()
    controller.run()
