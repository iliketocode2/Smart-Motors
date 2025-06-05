import network
import websocket
import ujson
import time
from machine import Pin, I2C
import math

# ADXL345 class
device = const(0x53)
regAddress = const(0x32)
TO_READ = 6
buff = bytearray(6)

class ADXL345:
    def __init__(self,i2c,addr=device):
        self.addr = addr
        self.i2c = i2c
        b = bytearray(1)
        b[0] = 0
        self.i2c.writeto_mem(self.addr,0x2d,b)
        b[0] = 16
        self.i2c.writeto_mem(self.addr,0x2d,b)
        b[0] = 8
        self.i2c.writeto_mem(self.addr,0x2d,b)
    
    @property
    def xValue(self):
        buff = self.i2c.readfrom_mem(self.addr,regAddress,TO_READ)
        x = (int(buff[1]) << 8) | buff[0]
        if x > 32767:
            x -= 65536
        return x
   
    @property
    def yValue(self):
        buff = self.i2c.readfrom_mem(self.addr,regAddress,TO_READ)
        y = (int(buff[3]) << 8) | buff[2]
        if y > 32767:
            y -= 65536
        return y
     
    @property   
    def zValue(self): 
        buff = self.i2c.readfrom_mem(self.addr,regAddress,TO_READ)
        z = (int(buff[5]) << 8) | buff[4]
        if z > 32767:
            z -= 65536
        return z
           
    def RP_calculate(self,x,y,z):
        roll = math.atan2(y , z) * 57.3
        pitch = math.atan2((- x) , math.sqrt(y * y + z * z)) * 57.3
        return roll,pitch

# WiFi credentials
SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"

# WebSocket URL - matches PyScript channel
WS_URL = "wss://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon"

class SmartMotorController:
    def __init__(self):
        self.ws = None
        self.adxl = None
        self.last_send = 0
        self.send_interval = 1000  # Send every 1 second (milliseconds)
        
        # Initialize components
        self.setup_wifi()
        self.setup_accelerometer()
        self.setup_websocket()
    
    def setup_wifi(self):
        """Connect to WiFi network"""
        print("SmartMotor Controller Starting...")
        
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if not wlan.isconnected():
            print("Connecting to WiFi...")
            wlan.connect(SSID, PASSWORD)
            
            while not wlan.isconnected():
                print(".", end="")
                time.sleep(0.5)
        
        print(f"\nWiFi connected! IP: {wlan.ifconfig()[0]}")
    
    def setup_accelerometer(self):
        """Initialize ADXL345 accelerometer"""
        try:
            i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
            self.adxl = ADXL345(i2c)
            print("ADXL345 accelerometer initialized")
        except Exception as e:
            print(f"Accelerometer setup error: {e}")
            self.adxl = None
    
    def setup_websocket(self):
        """Initialize WebSocket connection"""
        try:
            self.ws = websocket.websocket(WS_URL)
            self.ws.settimeout(5.0)
            print("WebSocket connected!")
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.ws = None
    
    def send_accelerometer_data(self):
        """Read accelerometer and send data via WebSocket"""
        if not self.adxl or not self.ws:
            return
        
        try:
            # Read accelerometer data from ADXL345
            x = self.adxl.xValue
            y = self.adxl.yValue
            z = self.adxl.zValue
            
            # Convert raw values to g-force (ADXL345 sensitivity: ~256 counts/g at ±2g range)
            accel_x = x / 256.0
            accel_y = y / 256.0
            accel_z = z / 256.0
            
            # You can choose which axis to send, or send all three
            # Using Z-axis for consistency with your original setup
            accel_value = accel_z
            
            # Optional: Calculate roll/pitch if needed
            # roll, pitch = self.adxl.RP_calculate(x, y, z)
            
            # Create message matching PyScript channel format
            message = {
                "topic": "/SM/accel",
                "value": accel_value
            }
            
            # Send JSON message
            json_msg = ujson.dumps(message)
            self.ws.send(json_msg)
            
            print(f"Sent: {json_msg} (X:{accel_x:.2f}g, Y:{accel_y:.2f}g, Z:{accel_z:.2f}g)")
            
        except Exception as e:
            print(f"Send error: {e}")
            # Try to reconnect WebSocket
            self.reconnect_websocket()
    
    def handle_received_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            data = ujson.loads(message)
            topic = data.get("topic", "")
            value = data.get("value", "")
            
            print(f"Received - Topic: {topic}, Value: {value}")
            
            # Handle any controller-specific commands here if needed
            
        except Exception as e:
            print(f"Message handling error: {e}")
    
    def reconnect_websocket(self):
        """Attempt to reconnect WebSocket"""
        try:
            if self.ws:
                self.ws.close()
            self.ws = websocket.websocket(WS_URL)
            self.ws.settimeout(5.0)
            print("WebSocket reconnected!")
        except Exception as e:
            print(f"Reconnection failed: {e}")
            self.ws = None
    
    def run(self):
        """Main loop"""
        print("Controller running - sending accelerometer data...")
        
        while True:
            try:
                # Send accelerometer data periodically
                current_time = time.ticks_ms()
                if time.ticks_diff(current_time, self.last_send) > self.send_interval:
                    self.send_accelerometer_data()
                    self.last_send = current_time
                
                # Check for incoming messages (non-blocking)
                if self.ws:
                    try:
                        # Set a very short timeout for non-blocking receive
                        self.ws.settimeout(0.01)
                        message = self.ws.recv()
                        if message:
                            self.handle_received_message(message)
                    except OSError:
                        # Timeout or no message - this is normal
                        pass
                    except Exception as e:
                        print(f"Receive error: {e}")
                        self.reconnect_websocket()
                    finally:
                        # Reset timeout
                        if self.ws:
                            self.ws.settimeout(5.0)
                
                time.sleep(0.01)  # Small delay
                
            except KeyboardInterrupt:
                print("Controller stopped by user")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                time.sleep(1)
        
        # Cleanup
        if self.ws:
            self.ws.close()

# Run the controller
if __name__ == "__main__":
    controller = SmartMotorController()
    controller.run()
