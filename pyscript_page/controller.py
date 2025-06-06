import network
import usocket as socket
import ujson
import time
import ubinascii
import hashlib
from machine import Pin, SoftI2C
import sensors
import ssd1306
import icons

# WiFi credentials
SSID = "tufts_eecs"
PASSWORD = "------"

# WebSocket server details - Updated for your PyScript server
WS_HOST = "chrisrogers.pyscriptapps.com"
WS_PORT = 443  # HTTPS/WSS port
WS_PATH = "/talking-on-a-channel/api/channels/hackathon"

class SmartMotorController:
    def __init__(self):
        self.sensor_system = None
        self.display = None
        self.ws = None
        self.last_send = 0
        self.send_interval = 1000  # Send every 1 second
        self.display_update_interval = 500
        self.last_display_update = 0
        self.connection_status = "Starting"
        
        # Initialize components
        self.setup_display()
        self.setup_wifi()
        self.setup_sensors()
    
    def setup_display(self):
        """Initialize OLED display"""
        try:
            i2c = SoftI2C(scl=Pin(7), sda=Pin(6))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))
            
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 15)
            self.display.text("Controller", 25, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()
            print("OLED display initialized")
        except Exception as e:
            print(f"Display setup error: {e}")
            self.display = None
    
    def update_display(self, status, wifi_status, sensor_data=None):
        """Update OLED display with current status"""
        if not self.display:
            return
        
        try:
            self.display.fill(0)
            self.display.text("CONTROLLER", 20, 0)
            self.display.text(f"WiFi: {wifi_status}", 0, 15)
            self.display.text(f"WS: {status}", 0, 25)
            
            if sensor_data:
                self.display.text(f"Roll: {sensor_data['roll']:.1f}", 0, 35)
                self.display.text(f"Pitch: {sensor_data['pitch']:.1f}", 0, 45)
                self.display.text(f"Send: {'OK' if sensor_data.get('sent') else 'FAIL'}", 0, 55)
            
            self.display.show()
        except Exception as e:
            print(f"Display update error: {e}")
    
    def setup_wifi(self):
        """Connect to WiFi network"""
        print("SmartMotor Controller Starting...")
        
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if not wlan.isconnected():
            if self.display:
                self.display.fill(0)
                self.display.text("Connecting WiFi", 10, 20)
                self.display.text(SSID[:16], 10, 35)
                self.display.show()
            
            print(f"Connecting to WiFi: {SSID}")
            
            try:
                wlan.connect(SSID, PASSWORD)
                
                max_wait = 30
                wait_count = 0
                
                while not wlan.isconnected() and wait_count < max_wait:
                    print(".", end="")
                    time.sleep(1)
                    wait_count += 1
                
                if wlan.isconnected():
                    config = wlan.ifconfig()
                    print(f"\nWiFi connected successfully!")
                    print(f"IP address: {config[0]}")
                    
                    if self.display:
                        self.display.fill(0)
                        self.display.text("WiFi Connected", 10, 20)
                        self.display.text(config[0], 10, 35)
                        self.display.show()
                        time.sleep(2)
                else:
                    print(f"\nWiFi connection failed")
                    
            except Exception as e:
                print(f"WiFi connection error: {e}")
        else:
            print("Already connected to WiFi")
    
    def setup_sensors(self):
        """Initialize sensor system"""
        try:
            print("Initializing sensor system...")
            self.sensor_system = sensors.SENSORS()
            print("Sensor system initialized successfully")
        except Exception as e:
            print(f"Sensor setup error: {e}")
            self.sensor_system = None
    
    def generate_websocket_key(self):
        """Generate a random WebSocket key"""
        import urandom
        key = ubinascii.b2a_base64(urandom.getrandbits(128).to_bytes(16, 'big')).decode().strip()
        return key
    
    def connect_websocket(self):
        """Connect to WebSocket server with proper handshake for WSS"""
        try:
            print(f"Connecting to WebSocket: wss://{WS_HOST}{WS_PATH}")
            
            # Import SSL for secure connection
            try:
                import ssl
            except ImportError:
                print("SSL not available - trying plain WebSocket")
                return self.connect_websocket_plain()
            
            # Create socket and wrap with SSL
            raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_socket.settimeout(15)
            
            # Get server address
            addr = socket.getaddrinfo(WS_HOST, WS_PORT)[0][-1]
            raw_socket.connect(addr)
            
            # Wrap with SSL
            self.ws = ssl.wrap_socket(raw_socket, server_hostname=WS_HOST)
            
            # Generate WebSocket key
            ws_key = self.generate_websocket_key()
            
            # Send WebSocket handshake
            handshake = (
                f"GET {WS_PATH} HTTP/1.1\r\n"
                f"Host: {WS_HOST}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Origin: https://esp32-controller\r\n"
                "User-Agent: ESP32-WebSocket-Client\r\n"
                "\r\n"
            )
            
            self.ws.send(handshake.encode())
            
            # Wait for handshake response
            response = self.ws.recv(1024).decode()
            print(f"WebSocket handshake response: {response[:200]}...")
            
            if "101 Switching Protocols" in response:
                print("✓ WebSocket connection established")
                self.connection_status = "Connected"
                self.ws.settimeout(1)  # Set shorter timeout for normal operation
                return True
            else:
                print("✗ WebSocket handshake failed")
                print(f"Full response: {response}")
                self.ws.close()
                self.ws = None
                self.connection_status = "Handshake Failed"
                return False
                
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
            self.ws = None
            self.connection_status = "Connection Error"
            return False
    
    def connect_websocket_plain(self):
        """Fallback to plain WebSocket if SSL fails"""
        try:
            print("Attempting plain WebSocket connection...")
            
            # Create socket
            self.ws = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.ws.settimeout(15)
            
            # Connect to port 80 for plain WebSocket
            addr = socket.getaddrinfo(WS_HOST, 80)[0][-1]
            self.ws.connect(addr)
            
            # Generate WebSocket key
            ws_key = self.generate_websocket_key()
            
            # Send WebSocket handshake
            handshake = (
                f"GET {WS_PATH} HTTP/1.1\r\n"
                f"Host: {WS_HOST}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Origin: http://esp32-controller\r\n"
                "\r\n"
            )
            
            self.ws.send(handshake.encode())
            
            # Wait for handshake response
            response = self.ws.recv(1024).decode()
            print(f"Plain WebSocket response: {response[:200]}...")
            
            if "101 Switching Protocols" in response:
                print("✓ Plain WebSocket connection established")
                self.connection_status = "Connected"
                self.ws.settimeout(1)
                return True
            else:
                print("✗ Plain WebSocket handshake failed")
                self.ws.close()
                self.ws = None
                self.connection_status = "Handshake Failed"
                return False
                
        except Exception as e:
            print(f"Plain WebSocket error: {e}")
            if self.ws:
                self.ws.close()
            self.ws = None
            self.connection_status = "Plain WS Error"
            return False
    
    def send_websocket_frame(self, data):
        """Send a WebSocket text frame"""
        if not self.ws:
            return False
            
        try:
            # Convert data to JSON string
            json_data = ujson.dumps(data)
            payload = json_data.encode('utf-8')
            payload_len = len(payload)
            
            print(f"Sending: {json_data}")  # Debug output
            
            # Create WebSocket frame
            frame = bytearray()
            
            # First byte: FIN (1) + RSV (000) + Opcode (0001 for text)
            frame.append(0x81)
            
            # Second byte: MASK (1) + Payload length
            if payload_len < 126:
                frame.append(0x80 | payload_len)
            elif payload_len < 65536:
                frame.append(0x80 | 126)
                frame.extend(payload_len.to_bytes(2, 'big'))
            else:
                frame.append(0x80 | 127)
                frame.extend(payload_len.to_bytes(8, 'big'))
            
            # Masking key (4 bytes)
            import urandom
            mask = urandom.getrandbits(32).to_bytes(4, 'big')
            frame.extend(mask)
            
            # Masked payload
            masked_payload = bytearray()
            for i, byte in enumerate(payload):
                masked_payload.append(byte ^ mask[i % 4])
            frame.extend(masked_payload)
            
            # Send frame
            self.ws.send(frame)
            return True
            
        except Exception as e:
            print(f"WebSocket send error: {e}")
            self.connection_status = "Send Error"
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
            self.ws = None
            return False
    
    def send_sensor_data(self):
        """Read sensors and send data via WebSocket"""
        if not self.sensor_system:
            return False
        
        try:
            # Read sensor data
            x, y, z = self.sensor_system.readaccel()
            roll, pitch = self.sensor_system.readroll()
            
            # Create message with channel info for PyScript server
            message = {
                "type": "sensor_data",
                "device": "controller",
                "channel": "hackathon",
                "data": {
                    "roll": round(roll, 2),
                    "pitch": round(pitch, 2),
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "z": round(z, 2),
                    "timestamp": time.ticks_ms()
                }
            }
            
            # Send via WebSocket
            success = self.send_websocket_frame(message)
            
            if success:
                print(f"📡 Sent: Roll={roll:.1f}°, Pitch={pitch:.1f}°")
                self.connection_status = "Sending"
            else:
                print("✗ Failed to send data")
                self.connection_status = "Send Failed"
            
            return success
            
        except Exception as e:
            print(f"Sensor read error: {e}")
            return False
    
    def run(self):
        """Main loop"""
        print("Controller running - sending sensor data via WebSocket...")
        print("Press Ctrl+C to stop")
        
        wlan = network.WLAN(network.STA_IF)
        
        try:
            while True:
                current_time = time.ticks_ms()
                sensor_data = {}
                
                # Check WiFi connection
                if not wlan.isconnected():
                    print("WiFi disconnected, reconnecting...")
                    self.setup_wifi()
                    continue
                
                # Connect WebSocket if not connected
                if not self.ws:
                    print("WebSocket not connected, attempting to connect...")
                    if self.connect_websocket():
                        print("WebSocket connected successfully!")
                    else:
                        print("WebSocket connection failed, waiting before retry...")
                        time.sleep(5)
                        continue
                
                # Read sensor data
                if self.sensor_system:
                    try:
                        x, y, z = self.sensor_system.readaccel()
                        roll, pitch = self.sensor_system.readroll()
                        sensor_data = {
                            'roll': roll,
                            'pitch': pitch,
                            'x': x, 'y': y, 'z': z
                        }
                    except Exception as e:
                        print(f"Sensor read error: {e}")
                
                # Send data at regular intervals
                if time.ticks_diff(current_time, self.last_send) > self.send_interval:
                    if sensor_data:
                        send_success = self.send_sensor_data()
                        sensor_data['sent'] = send_success
                        if not send_success:
                            # Reconnect on send failure
                            self.ws = None
                    self.last_send = current_time
                
                # Update display
                if time.ticks_diff(current_time, self.last_display_update) > self.display_update_interval:
                    wifi_status = "Connected" if wlan.isconnected() else "Disconnected"
                    self.update_display(self.connection_status, wifi_status, sensor_data if sensor_data else None)
                    self.last_display_update = current_time
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            print("\nController stopped by user")
            if self.display:
                self.display.fill(0)
                self.display.text("STOPPED", 35, 30)
                self.display.show()
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(2)
        finally:
            # Cleanup
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
                print("WebSocket connection closed")

# Auto-run when uploaded to ESP32
if __name__ == "__main__":
    print("="*60)
    print("ESP32 SMART MOTOR CONTROLLER - PyScript WebSocket Version")
    print("SETUP REQUIRED:")
    print("1. Set SSID and PASSWORD for your WiFi")
    print("2. Upload sensors.py and adxl345.py to ESP32")
    print("3. Connect ADXL345 accelerometer to I2C pins")
    print("4. Connect OLED display to I2C (SCL=7, SDA=6)")
    print("5. Save this file as 'main.py' to auto-run on boot")
    print("="*60)
    
    controller = SmartMotorController()
    controller.run()
