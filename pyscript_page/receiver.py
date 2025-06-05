import network
import websocket
import ujson
import time
from machine import Pin, PWM

# WiFi credentials
SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"

# WebSocket URL - matches PyScript channel
WS_URL = "wss://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon"

class SmartMotorReceiver:
    def __init__(self):
        self.ws = None
        self.servo = None
        self.servo_pin = 2  # GPIO pin for servo
        
        # Initialize components
        self.setup_wifi()
        self.setup_servo()
        self.setup_websocket()
    
    def setup_wifi(self):
        """Connect to WiFi network"""
        print("SmartMotor Receiver Starting...")
        
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        
        if not wlan.isconnected():
            print("Connecting to WiFi...")
            wlan.connect(SSID, PASSWORD)
            
            while not wlan.isconnected():
                print(".", end="")
                time.sleep(0.5)
        
        print(f"\nWiFi connected! IP: {wlan.ifconfig()[0]}")
    
    def setup_servo(self):
        """Initialize servo motor"""
        try:
            self.servo = PWM(Pin(self.servo_pin))
            self.servo.freq(50)  # 50Hz for servo
            self.move_servo(90)  # Start at center position
            print("Servo initialized at 90 degrees")
        except Exception as e:
            print(f"Servo setup error: {e}")
    
    def setup_websocket(self):
        """Initialize WebSocket connection"""
        try:
            self.ws = websocket.websocket(WS_URL)
            self.ws.settimeout(5.0)
            print("WebSocket connected - listening for servo commands")
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.ws = None
    
    def move_servo(self, angle):
        """Move servo to specified angle (0-180 degrees)"""
        if not self.servo:
            return
        
        try:
            # Clamp angle to valid range
            angle = max(0, min(180, angle))
            
            # Convert angle to duty cycle
            # Servo expects pulse width: 0.5ms (0°) to 2.5ms (180°)
            # At 50Hz: 0.5ms = 2.5% duty, 2.5ms = 12.5% duty
            duty = int(25 + (angle * 102) / 180)  # Map 0-180° to 25-127 duty
            
            self.servo.duty(duty)
            print(f"Moved servo to: {angle} degrees")
            
        except Exception as e:
            print(f"Servo movement error: {e}")
    
    def send_servo_response(self, angle):
        """Send confirmation that servo moved"""
        if not self.ws:
            return
            
        try:
            response = {
                "topic": "/SM/servo",
                "value": angle,
                "status": "moved"
            }
            
            json_response = ujson.dumps(response)
            self.ws.send(json_response)
            
            print(f"Sent response: {json_response}")
            
        except Exception as e:
            print(f"Response send error: {e}")
    
    def handle_received_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            data = ujson.loads(message)
            topic = data.get("topic", "")
            
            # Check if this is accelerometer data from controller
            if topic == "/SM/accel":
                accel_value = data.get("value", 0)
                
                # Convert accelerometer value to servo angle
                # Using similar logic to your original code
                servo_angle = int(abs(accel_value * 90))  # Scale and get absolute value
                
                # Clamp to servo range
                servo_angle = max(0, min(180, servo_angle))
                
                # Move servo
                self.move_servo(servo_angle)
                
                # Send confirmation back to channel
                self.send_servo_response(servo_angle)
            
            else:
                print(f"Received other message - Topic: {topic}, Value: {data.get('value', '')}")
                
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
        """Main loop - listen for messages"""
        print("Receiver running - waiting for accelerometer data...")
        
        while True:
            try:
                if self.ws:
                    try:
                        # Wait for incoming messages
                        message = self.ws.recv()
                        if message:
                            print(f"Received: {message}")
                            self.handle_received_message(message)
                    
                    except OSError as e:
                        # Timeout or connection error
                        if "timeout" not in str(e).lower():
                            print(f"Connection error: {e}")
                            self.reconnect_websocket()
                    
                    except Exception as e:
                        print(f"Receive error: {e}")
                        self.reconnect_websocket()
                
                else:
                    # Try to reconnect if no WebSocket connection
                    print("No WebSocket connection, attempting to reconnect...")
                    self.reconnect_websocket()
                    time.sleep(5)
                
                time.sleep(0.01)  # Small delay
                
            except KeyboardInterrupt:
                print("Receiver stopped by user")
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                time.sleep(1)
        
        # Cleanup
        if self.ws:
            self.ws.close()
        if self.servo:
            self.servo.deinit()

# Run the receiver
if __name__ == "__main__":
    receiver = SmartMotorReceiver()
    receiver.run()
