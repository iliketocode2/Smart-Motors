"""
ESP32 SmartMotor Controller - HTTP Bridge Version
Reads potentiometer and sends data to bridge server via HTTP
"""

import network
import urequests
import json
import time
import gc
from machine import Pin, ADC

# Configuration - Update these for your setup
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""
BRIDGE_SERVER_IP = ""  # Update to your bridge server IP
BRIDGE_PORT = 8080

# Hardware configuration
POTENTIOMETER_PIN = 3
DISPLAY_AVAILABLE = True  # Set to False if no display

# Communication settings
SEND_INTERVAL_MS = 200  # Send data every 200ms (5 times per second)
ANGLE_CHANGE_THRESHOLD = 2  # Only send if angle changed by 2+ degrees
WIFI_TIMEOUT = 30  # WiFi connection timeout in seconds

class SmartMotorController:
    def __init__(self):
        self.wlan = None
        self.last_angle_sent = 90
        self.last_send_time = 0
        self.send_count = 0
        self.error_count = 0
        
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
        
        print("SmartMotor Controller initialized")
        
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
    
    def read_potentiometer(self):
        """Read potentiometer value and convert to angle"""
        try:
            # Read raw value (0-4095)
            raw_value = self.potentiometer.read()
            
            # Convert to angle (0-180 degrees)
            angle = int((180.0 / 4095.0) * raw_value)
            angle = max(0, min(180, angle))
            
            return angle
        except Exception as e:
            print(f"Potentiometer read error: {e}")
            return self.last_angle_sent
    
    def send_data_to_bridge(self, angle):
        """Send angle data to bridge server via HTTP"""
        try:
            url = f"http://{BRIDGE_SERVER_IP}:{BRIDGE_PORT}/api/controller"
            data = {"angle": angle}
            
            # Send HTTP POST request
            response = urequests.post(url, json=data, timeout=2)
            
            if response.status_code == 200:
                self.send_count += 1
                print(f"Sent angle: {angle}° (#{self.send_count})")
                response.close()
                return True
            else:
                print(f"Bridge server error: {response.status_code}")
                response.close()
                return False
                
        except Exception as e:
            self.error_count += 1
            print(f"Send error: {e}")
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
        print("Starting SmartMotor Controller...")
        
        # Connect to WiFi
        if not self.connect_wifi():
            print("Failed to connect to WiFi. Exiting.")
            return
        
        print(f"Bridge server: {BRIDGE_SERVER_IP}:{BRIDGE_PORT}")
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
                        # Send data to bridge
                        if self.send_data_to_bridge(angle):
                            self.last_angle_sent = angle
                            self.last_send_time = current_time
                            
                            # Update display
                            self.update_display(
                                "CONTROLLER",
                                f"Angle: {angle}°",
                                f"Sent: #{self.send_count}",
                                f"Errors: {self.error_count}"
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
                            f"Sent: #{self.send_count}"
                        )
                
                # Small delay to prevent overwhelming the system
                time.sleep_ms(50)
                
                # Periodic garbage collection
                if self.send_count % 50 == 0:
                    gc.collect()
                
            except KeyboardInterrupt:
                print("Shutting down...")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                self.error_count += 1
                time.sleep(1)

# Run the controller
if __name__ == "__main__":
    controller = SmartMotorController()
    controller.run()
