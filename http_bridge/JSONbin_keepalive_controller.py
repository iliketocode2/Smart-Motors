"""
ESP32 SmartMotor Controller - HTTP Keep-Alive Optimization
Reuses TCP connections to reduce HTTP overhead
"""

import network
import urequests
import json
import time
import gc
from machine import Pin, ADC

# Configuration
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""

JSONBIN_BIN_ID = ""
JSONBIN_API_KEY = ""
JSONBIN_BASE_URL = "https://api.jsonbin.io/v3/b"
JSONBIN_WRITE_URL = f"{JSONBIN_BASE_URL}/{JSONBIN_BIN_ID}"

# Hardware
POTENTIOMETER_PIN = 3
DISPLAY_AVAILABLE = True

# HTTP Keep-Alive optimized settings
SEND_INTERVAL_MS = 200
HTTP_TIMEOUT = 1
ANGLE_CHANGE_THRESHOLD = 1
MAX_RETRIES = 2
CONNECTION_REUSE_COUNT = 20     # Reuse connection for N requests

class HTTPKeepAliveController:
    def __init__(self):
        self.last_angle_sent = 90
        self.last_send_time = 0
        self.send_count = 0
        self.error_count = 0
        self.connection_reuse_counter = 0
        
        # HTTP Keep-Alive session management
        self.session_headers = {
            "Content-Type": "application/json",
            "X-Master-Key": JSONBIN_API_KEY,
            "Connection": "keep-alive",        # Keep TCP connection open
            "Cache-Control": "no-cache",       # Prevent caching delays
            "User-Agent": "ESP32-SmartMotor"   # Identify our requests
        }
        
        # Hardware setup
        self.potentiometer = ADC(Pin(POTENTIOMETER_PIN))
        self.potentiometer.atten(ADC.ATTN_11DB)
        
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
        
        print("HTTP Keep-Alive Controller initialized")
        
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
    
    def read_potentiometer(self):
        """Read potentiometer value"""
        try:
            raw_value = self.potentiometer.read()
            angle = int((180.0 / 4095.0) * raw_value)
            return max(0, min(180, angle))
        except:
            return self.last_angle_sent
    
    def send_data_with_keepalive(self, angle):
        """HTTP request with connection reuse optimization"""
        try:
            # Minimal data payload
            data = {"angle": angle, "count": self.send_count + 1, "timestamp": time.ticks_ms()}
            
            # Enhanced headers for keep-alive
            headers = self.session_headers.copy()
            
            # Add session management for connection reuse
            if self.connection_reuse_counter > 0:
                headers["Connection"] = "keep-alive"
            else:
                headers["Connection"] = "close"  # Force new connection periodically
            
            # Time the request
            start_time = time.ticks_ms()
            
            # Make HTTP request with keep-alive
            response = urequests.put(
                JSONBIN_WRITE_URL, 
                json=data, 
                headers=headers, 
                timeout=HTTP_TIMEOUT
            )
            
            # Calculate actual response time
            response_time = time.ticks_diff(time.ticks_ms(), start_time)
            
            if response.status_code == 200:
                self.send_count += 1
                self.connection_reuse_counter = (self.connection_reuse_counter + 1) % CONNECTION_REUSE_COUNT
                
                print(f"✅ Sent {angle}° in {response_time}ms (#{self.send_count})")
                response.close()
                return True, response_time
            else:
                print(f"❌ HTTP error {response.status_code}")
                response.close()
                return False, response_time
                
        except Exception as e:
            self.error_count += 1
            print(f"❌ Send error: {e}")
            
            # Reset connection counter on error
            self.connection_reuse_counter = 0
            return False, 0
    
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
        print("Starting HTTP Keep-Alive Controller...")
        
        if not self.connect_wifi():
            print("WiFi connection failed. Exiting.")
            return
        
        print(f"🔄 HTTP Keep-Alive Mode:")
        print(f"   📡 Send interval: {SEND_INTERVAL_MS}ms")
        print(f"   🔗 Connection reuse: {CONNECTION_REUSE_COUNT} requests")
        print(f"   ⏱️  Timeout: {HTTP_TIMEOUT}s")
        
        # Track response times for analysis
        response_times = []
        
        while True:
            try:
                current_time = time.ticks_ms()
                
                if time.ticks_diff(current_time, self.last_send_time) >= SEND_INTERVAL_MS:
                    # Read potentiometer
                    angle = self.read_potentiometer()
                    
                    # Check if angle changed
                    if abs(angle - self.last_angle_sent) >= ANGLE_CHANGE_THRESHOLD or self.send_count == 0:
                        
                        # Send with keep-alive optimization
                        success, response_time = self.send_data_with_keepalive(angle)
                        
                        if success:
                            self.last_angle_sent = angle
                            response_times.append(response_time)
                            
                            # Calculate average response time
                            if len(response_times) > 10:
                                response_times = response_times[-10:]  # Keep last 10
                            avg_response = sum(response_times) / len(response_times)
                            
                            # Update display with timing info
                            self.update_display(
                                "KEEP-ALIVE",
                                f"Sent: {angle}°",
                                f"Avg: {avg_response:.0f}ms",
                                f"#{self.send_count} E:{self.error_count}"
                            )
                        else:
                            # Error display
                            self.update_display(
                                "KEEP-ALIVE",
                                f"Angle: {angle}°",
                                "SEND FAILED",
                                f"#{self.send_count} E:{self.error_count}"
                            )
                    else:
                        # No change display
                        avg_response = sum(response_times) / len(response_times) if response_times else 0
                        self.update_display(
                            "KEEP-ALIVE",
                            f"Ready: {angle}°",
                            f"Avg: {avg_response:.0f}ms",
                            f"#{self.send_count}"
                        )
                    
                    self.last_send_time = current_time
                
                # Garbage collection
                if self.send_count % 10 == 0 and self.send_count > 0:
                    gc.collect()
                
                time.sleep_ms(50)
                
            except KeyboardInterrupt:
                print("Shutting down...")
                print(f"Final stats: {self.send_count} sends, {self.error_count} errors")
                if response_times:
                    print(f"Average response time: {sum(response_times)/len(response_times):.1f}ms")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.error_count += 1
                time.sleep(1)

if __name__ == "__main__":
    controller = HTTPKeepAliveController()
    controller.run()
