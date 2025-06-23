"""
ESP32 SmartMotor Controller - Direct TCP Client
Sends potentiometer data directly to receiver ESP32
"""

import network
import socket
import json
import time
import gc
from machine import Pin, ADC

# Configuration
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""

# TCP Configuration (replace with receiver ESP32's IP)
SERVER_IP = "192.168.1.100"  # CHANGE TO YOUR RECEIVER ESP32'S IP
SERVER_PORT = 4080

# Hardware
POTENTIOMETER_PIN = 3

# Communication settings
SEND_INTERVAL_MS = 200
RECONNECT_DELAY_MS = 3000
ANGLE_CHANGE_THRESHOLD = 2
CONNECTION_TIMEOUT = 5  # seconds

class TCPSmartMotorController:
    def __init__(self):
        self.device_id = "tcp_controller"
        
        # TCP connection state
        self.tcp_socket = None
        self.connected = False
        self.server_ip = SERVER_IP
        self.server_port = SERVER_PORT
        
        # Communication state
        self.last_angle_sent = 90
        self.last_send_time = 0
        self.last_reconnect_time = 0
        self.message_count = 0
        self.connection_attempts = 0
        
        # Hardware
        self.potentiometer = ADC(Pin(POTENTIOMETER_PIN))
        self.potentiometer.atten(ADC.ATTN_11DB)
        
        # Display
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
        
        print("TCP Controller initialized")
        print("Target server: {}:{}".format(self.server_ip, self.server_port))
    
    def connect_wifi(self):
        """Connect to WiFi"""
        print("Connecting to WiFi...")
        self.update_display("SmartMotor", "WiFi", "Connecting...", "")
        
        try:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
            
            # Check if already connected
            if wlan.isconnected():
                ip = wlan.ifconfig()[0]
                print("Already connected: {}".format(ip))
                self.update_display("SmartMotor", "WiFi OK", ip[:12], "")
                time.sleep(1)
                return True
            
            # Disconnect if partially connected
            try:
                wlan.disconnect()
                time.sleep(1)
            except:
                pass
            
            # Connect to network
            wlan.connect(WIFI_SSID, WIFI_PASSWORD)
            
            # Wait for connection
            timeout = 20
            while not wlan.isconnected() and timeout > 0:
                time.sleep(1)
                timeout -= 1
                
                if timeout % 5 == 0:
                    self.update_display("SmartMotor", "WiFi", "Wait {}s".format(20-timeout), "")
            
            if wlan.isconnected():
                ip = wlan.ifconfig()[0]
                print("WiFi connected: {}".format(ip))
                self.update_display("SmartMotor", "WiFi OK", ip[:12], "")
                time.sleep(1)
                return True
            else:
                print("WiFi connection timeout")
                self.update_display("SmartMotor", "WiFi Failed", "Timeout", "")
                return False
                
        except Exception as e:
            print("WiFi error: {}".format(str(e)))
            self.update_display("SmartMotor", "WiFi Error", str(e)[:12], "")
            return False
    
    def connect_tcp(self):
        """Connect to TCP server (receiver ESP32)"""
        try:
            print("Connecting to TCP server {}:{}...".format(self.server_ip, self.server_port))
            self.update_display("SmartMotor", "TCP", "Connecting...", "")
            
            # Clean up existing connection
            self.disconnect_tcp()
            
            # Create new TCP socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(CONNECTION_TIMEOUT)
            
            # Connect to server
            self.tcp_socket.connect((self.server_ip, self.server_port))
            
            # Set socket to non-blocking for normal operation
            self.tcp_socket.settimeout(0.1)
            
            self.connected = True
            self.connection_attempts += 1
            
            print("TCP connected successfully!")
            self.update_display("SmartMotor", "TCP Connected", "Ready to send", "")
            
            return True
            
        except Exception as e:
            print("TCP connection error: {}".format(str(e)))
            self.update_display("SmartMotor", "TCP Failed", str(e)[:12], "")
            self.disconnect_tcp()
            return False
    
    def send_tcp_message(self, angle):
        """Send angle data via TCP"""
        if not self.connected or not self.tcp_socket:
            return False
        
        try:
            # Create simple message (can be JSON or just the angle)
            message = {
                "angle": int(angle),
                "timestamp": time.ticks_ms(),
                "count": self.message_count + 1
            }
            
            # Convert to JSON and encode
            json_data = json.dumps(message)
            data = json_data.encode('utf-8')
            
            # Send data
            bytes_sent = self.tcp_socket.send(data + b'\n')  # Newline as delimiter
            
            if bytes_sent > 0:
                self.message_count += 1
                print("TCP sent: {}deg (#{})" .format(angle, self.message_count))
                return True
            else:
                print("TCP send failed: no bytes sent")
                self.connected = False
                return False
                
        except Exception as e:
            print("TCP send error: {}".format(str(e)))
            self.connected = False
            return False
    
    def check_tcp_connection(self):
        """Check if TCP connection is still alive"""
        if not self.tcp_socket:
            return False
        
        try:
            # Try to receive any response data (non-blocking)
            try:
                data = self.tcp_socket.recv(1024)
                if data:
                    print("Received TCP response: {}".format(data.decode('utf-8')))
            except OSError:
                # No data available - this is normal
                pass
                
            return self.connected
            
        except Exception as e:
            print("TCP connection check failed: {}".format(str(e)))
            self.connected = False
            return False
    
    def disconnect_tcp(self):
        """Disconnect TCP connection"""
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
            self.tcp_socket = None
        
        self.connected = False
    
    def read_potentiometer(self):
        """Read potentiometer with averaging"""
        try:
            readings = []
            for _ in range(3):
                readings.append(self.potentiometer.read())
                time.sleep_ms(1)
            
            avg = sum(readings) / len(readings)
            angle = int((180.0 / 4095.0) * avg)
            return max(0, min(180, angle))
        except:
            return self.last_angle_sent
    
    def should_send_data(self):
        """Check if should send potentiometer data"""
        current_angle = self.read_potentiometer()
        
        # Check if angle changed significantly
        if abs(current_angle - self.last_angle_sent) >= ANGLE_CHANGE_THRESHOLD:
            self.last_angle_sent = current_angle
            return True, current_angle
        
        return False, current_angle
    
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
        """Main execution loop"""
        print("Starting TCP SmartMotor Controller...")
        print("Direct ESP32-to-ESP32 communication")
        print("No external servers required!")
        
        # Connect to WiFi
        if not self.connect_wifi():
            print("Failed to connect to WiFi")
            return
        
        # Get WiFi IP for display
        wlan = network.WLAN(network.STA_IF)
        my_ip = wlan.ifconfig()[0]
        print("Controller IP: {}".format(my_ip))
        print("Target server: {}:{}".format(self.server_ip, self.server_port))
        print("Please ensure receiver ESP32 is running and accessible!")
        
        # Main communication loop
        while True:
            try:
                current_time = time.ticks_ms()
                
                # Check/establish TCP connection
                if not self.connected:
                    if time.ticks_diff(current_time, self.last_reconnect_time) >= RECONNECT_DELAY_MS:
                        self.last_reconnect_time = current_time
                        print("Attempting TCP connection...")
                        if self.connect_tcp():
                            print("TCP connection established")
                        else:
                            print("TCP connection failed, will retry...")
                            time.sleep(1)
                            continue
                
                # Check connection health
                if self.connected and not self.check_tcp_connection():
                    print("TCP connection lost")
                    self.disconnect_tcp()
                    continue
                
                # Send data if needed
                should_send, angle = self.should_send_data()
                if should_send and self.connected:
                    if time.ticks_diff(current_time, self.last_send_time) >= SEND_INTERVAL_MS:
                        if self.send_tcp_message(angle):
                            self.last_send_time = current_time
                            
                            # Update display
                            self.update_display(
                                "TCP CONTROLLER",
                                "Angle: {}deg".format(angle),
                                "Sent: #{}".format(self.message_count),
                                "Connected"
                            )
                        else:
                            print("TCP send failed")
                            self.disconnect_tcp()
                
                # Status display when not sending
                if self.connected and not should_send:
                    self.update_display(
                        "TCP CONTROLLER",
                        "Angle: {}deg".format(angle),
                        "Ready: #{}".format(self.message_count),
                        "{}:{}".format(self.server_ip[-8:], self.server_port)
                    )
                elif not self.connected:
                    self.update_display(
                        "TCP CONTROLLER",
                        "Angle: {}deg".format(angle),
                        "Disconnected",
                        "Attempts: {}".format(self.connection_attempts)
                    )
                
                # Garbage collection
                if self.message_count % 50 == 0 and self.message_count > 0:
                    gc.collect()
                
                time.sleep_ms(20)
                
            except KeyboardInterrupt:
                print("Shutdown requested")
                break
            except Exception as e:
                print("Main loop error: {}".format(str(e)))
                time.sleep(1)
        
        # Cleanup
        self.disconnect_tcp()
        print("TCP Controller stopped")

if __name__ == "__main__":
    controller = TCPSmartMotorController()
    controller.run()
