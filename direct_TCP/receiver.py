"""
ESP32 SmartMotor Receiver - Direct TCP Server
Receives potentiometer data directly from controller ESP32
"""

import network
import socket
import json
import time
import gc
from machine import Pin, PWM

# Configuration
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""

# TCP Configuration
SERVER_PORT = 4080

# Hardware
SERVO_PIN = 2

# Communication settings
MAX_CLIENTS = 1  # Only one controller at a time
SOCKET_TIMEOUT = 0.1  # Non-blocking socket operations

class SimpleServo:
    """Simple servo controller"""
    def __init__(self, pin, freq=50, min_us=600, max_us=2400):
        self.min_us = min_us
        self.max_us = max_us
        self.freq = freq
        self.pwm = PWM(pin, freq=freq, duty=0)
        self.current_angle = 90
        
    def write_angle(self, degrees):
        try:
            degrees = max(0, min(180, int(degrees)))
            if abs(degrees - self.current_angle) < 1:
                return True  # Skip very small changes
            
            us = self.min_us + (self.max_us - self.min_us) * degrees / 180
            duty = int(us * 1024 * self.freq / 1000000)
            self.pwm.duty(duty)
            self.current_angle = degrees
            return True
        except:
            return False

class TCPSmartMotorReceiver:
    def __init__(self):
        self.device_id = "tcp_receiver"
        
        # TCP server state
        self.server_socket = None
        self.client_socket = None
        self.client_address = None
        self.server_running = False
        self.my_ip = ""
        
        # Communication state
        self.current_servo_angle = 90
        self.message_count = 0
        self.client_connections = 0
        
        # Message buffer for incomplete messages
        self.message_buffer = ""
        
        # Hardware
        self.servo = SimpleServo(Pin(SERVO_PIN))
        self.servo.write_angle(90)
        print("Servo initialized and centered")
        
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
        
        print("TCP Receiver initialized")
    
    def connect_wifi(self):
        """Connect to WiFi"""
        print("Connecting to WiFi...")
        self.update_display("SmartMotor", "WiFi", "Connecting...", "")
        
        try:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
            
            # Check if already connected
            if wlan.isconnected():
                self.my_ip = wlan.ifconfig()[0]
                print("Already connected: {}".format(self.my_ip))
                self.update_display("SmartMotor", "WiFi OK", self.my_ip[:12], "")
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
                self.my_ip = wlan.ifconfig()[0]
                print("WiFi connected: {}".format(self.my_ip))
                self.update_display("SmartMotor", "WiFi OK", self.my_ip[:12], "")
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
    
    def start_tcp_server(self):
        """Start TCP server (like Arduino WiFiServer)"""
        try:
            print("Starting TCP server on port {}...".format(SERVER_PORT))
            self.update_display("SmartMotor", "TCP Server", "Starting...", "")
            
            # Create server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to all interfaces on specified port
            self.server_socket.bind(('', SERVER_PORT))
            
            # Start listening
            self.server_socket.listen(MAX_CLIENTS)
            
            # Set non-blocking
            self.server_socket.settimeout(SOCKET_TIMEOUT)
            
            self.server_running = True
            
            print("TCP server started successfully!")
            print("Server address: {}:{}".format(self.my_ip, SERVER_PORT))
            print("Update controller with SERVER_IP = \"{}\"".format(self.my_ip))
            
            self.update_display("SmartMotor", "TCP Server", "Listening", "{}:{}".format(self.my_ip[-8:], SERVER_PORT))
            
            return True
            
        except Exception as e:
            print("TCP server start error: {}".format(str(e)))
            self.update_display("SmartMotor", "TCP Failed", str(e)[:12], "")
            return False
    
    def accept_client(self):
        """Accept new client connection (non-blocking)"""
        if not self.server_running or not self.server_socket:
            return False
        
        try:
            # Try to accept a connection (non-blocking)
            client_socket, client_address = self.server_socket.accept()
            
            # Close any existing client
            self.disconnect_client()
            
            # Set new client
            self.client_socket = client_socket
            self.client_address = client_address
            self.client_connections += 1
            
            print("Client connected from: {}".format(client_address[0]))
            
            # Set client socket to non-blocking
            self.client_socket.settimeout(SOCKET_TIMEOUT)
            
            return True
            
        except OSError:
            # No connection available - normal for non-blocking
            return False
        except Exception as e:
            print("Accept client error: {}".format(str(e)))
            return False
    
    def receive_data(self):
        """Receive data from connected client"""
        if not self.client_socket:
            return []
        
        try:
            # Receive data (non-blocking)
            data = self.client_socket.recv(1024)
            
            if not data:
                # Client disconnected
                print("Client disconnected")
                self.disconnect_client()
                return []
            
            # Add to message buffer
            self.message_buffer += data.decode('utf-8')
            
            # Extract complete messages (separated by newlines)
            messages = []
            while '\n' in self.message_buffer:
                line, self.message_buffer = self.message_buffer.split('\n', 1)
                if line.strip():
                    messages.append(line.strip())
            
            return messages
            
        except OSError:
            # No data available - normal for non-blocking
            return []
        except Exception as e:
            print("Receive data error: {}".format(str(e)))
            self.disconnect_client()
            return []
    
    def process_message(self, message_text):
        """Process received message and move servo"""
        try:
            # Parse JSON message
            message = json.loads(message_text)
            
            # Extract angle
            angle = message.get('angle')
            if angle is not None and isinstance(angle, (int, float)):
                angle = int(angle)
                
                # Move servo
                if self.move_servo(angle):
                    self.message_count += 1
                    self.current_servo_angle = angle
                    
                    print("Moved servo to {}° (#{})" .format(angle, self.message_count))
                    
                    # Send response back to client (optional)
                    self.send_response(angle)
                    
                    return True
            
        except Exception as e:
            print("Message processing error: {}".format(str(e)))
        
        return False
    
    def send_response(self, angle):
        """Send response back to client (optional)"""
        if not self.client_socket:
            return
        
        try:
            response = {
                "status": "ok",
                "angle": angle,
                "timestamp": time.ticks_ms()
            }
            
            response_data = json.dumps(response).encode('utf-8') + b'\n'
            self.client_socket.send(response_data)
            
        except Exception as e:
            print("Send response error: {}".format(str(e)))
    
    def move_servo(self, angle):
        """Move servo to specified angle"""
        try:
            if self.servo.write_angle(angle):
                return True
        except Exception as e:
            print("Servo error: {}".format(str(e)))
        return False
    
    def disconnect_client(self):
        """Disconnect current client"""
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
            self.client_address = None
            self.message_buffer = ""
    
    def stop_server(self):
        """Stop TCP server"""
        self.server_running = False
        
        self.disconnect_client()
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        print("TCP server stopped")
    
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
        print("Starting TCP SmartMotor Receiver...")
        print("Direct ESP32-to-ESP32 communication")
        print("No external servers required!")
        
        # Connect to WiFi
        if not self.connect_wifi():
            print("Failed to connect to WiFi")
            return
        
        # Start TCP server
        if not self.start_tcp_server():
            print("Failed to start TCP server")
            return
        
        print("=" * 50)
        print("IMPORTANT: Update controller with this IP address:")
        print("SERVER_IP = \"{}\"".format(self.my_ip))
        print("=" * 50)
        
        # Main communication loop
        last_status_time = 0
        
        while True:
            try:
                current_time = time.ticks_ms()
                
                # Accept new clients if none connected
                if not self.client_socket:
                    self.accept_client()
                
                # Receive and process messages from connected client
                if self.client_socket:
                    messages = self.receive_data()
                    for message_text in messages:
                        self.process_message(message_text)
                
                # Update display periodically
                if time.ticks_diff(current_time, last_status_time) >= 1000:
                    last_status_time = current_time
                    
                    if self.client_socket:
                        client_ip = self.client_address[0] if self.client_address else "Unknown"
                        self.update_display(
                            "TCP RECEIVER",
                            "Servo: {}°".format(self.current_servo_angle),
                            "Client: {}".format(client_ip[-8:]),
                            "Msgs: #{}".format(self.message_count)
                        )
                    else:
                        self.update_display(
                            "TCP RECEIVER",
                            "Servo: {}°".format(self.current_servo_angle),
                            "Waiting...",
                            "{}:{}".format(self.my_ip[-8:], SERVER_PORT)
                        )
                
                # Garbage collection
                if self.message_count % 100 == 0 and self.message_count > 0:
                    gc.collect()
                
                time.sleep_ms(10)
                
            except KeyboardInterrupt:
                print("Shutdown requested")
                break
            except Exception as e:
                print("Main loop error: {}".format(str(e)))
                time.sleep(1)
        
        # Cleanup
        self.stop_server()
        self.servo.write_angle(90)  # Return to center
        print("TCP Receiver stopped")

if __name__ == "__main__":
    receiver = TCPSmartMotorReceiver()
    receiver.run()
