import time
import ujson
import sys
from machine import Pin
import servo
from websocket_base import WebSocketBase

class SmartMotorReceiver(WebSocketBase):
    def __init__(self):
        super().__init__()
        self.servo_motor = None
        self.servo_pin = 2
        self.current_angle = 90
        self.last_data_received = 0
        self.display_update_interval = 500
        self.last_display_update = 0
        self.last_roll = None
        self.setup_servo()
        
        # Update display title
        if self.display:
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 15)
            self.display.text("Receiver", 30, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()

    def setup_servo(self):
        """Initialize the servo motor"""
        try:
            self.servo_motor = servo.Servo(Pin(self.servo_pin))
            self.move_servo(90)
            print("Servo initialized on pin {} at 90°".format(self.servo_pin))
        except Exception as e:
            print("Servo setup error: {}".format(e))

    def move_servo(self, angle):
        """Move servo to specified angle"""
        if not self.servo_motor:
            print("No servo available")
            return
        angle = max(0, min(180, angle))
        if abs(angle - self.current_angle) > 2:
            self.servo_motor.write_angle(degrees=angle)
            self.current_angle = angle
            print("Moved servo to: {} deg".format(angle))

    def process_channel_message(self, message):
        """Process received channel message"""
        try:
            msg_type = message.get("type", "")
            payload = message.get("payload", {})
            
            if msg_type == "message":
                topic = payload.get("topic", "")
                value = payload.get("value", "")
                
                print("Channel message - Topic: {}, Value: {}".format(topic, value))
                
                # Handle sensor data from controller
                if topic == "/SM/accel":
                    try:
                        # Parse sensor data
                        sensor_data = ujson.loads(value) if isinstance(value, str) else value
                        if "roll" in sensor_data:
                            roll = sensor_data["roll"]
                            self.last_roll = roll
                            
                            # Convert roll to servo angle (adjust mapping as needed)
                            # Map roll from -90 to +90 degrees to servo range 0-180
                            servo_angle = 90 + (roll * 0.8)  # Scale factor for smoother movement
                            servo_angle = max(0, min(180, servo_angle))
                            
                            self.move_servo(servo_angle)
                            self.last_data_received = time.ticks_ms()
                            
                            print("Processed roll: {}, Servo: {}".format(roll, servo_angle))
                            
                            # Send confirmation back
                            response = {
                                "type": "message",
                                "payload": {
                                    "topic": "/SM/servo_response",
                                    "value": ujson.dumps({
                                        "servo_angle": servo_angle,
                                        "received_roll": roll,
                                        "timestamp": time.ticks_ms(),
                                        "source": "receiver"
                                    })
                                }
                            }
                            self.send_websocket_frame(response)
                            
                    except Exception as e:
                        print("Error processing sensor data: {}".format(e))
                        
        except Exception as e:
            print("Error processing channel message: {}".format(e))

    def update_display_status(self):
        """Display status updater for receiver"""
        if not self.display:
            return
            
        wlan = network.WLAN(network.STA_IF)
        wifi_status = "Connected" if wlan.isconnected() else "Disconnected"
        
        self.display.fill(0)
        self.display.text("RECEIVER", 25, 0)
        self.display.text(f"WiFi: {wifi_status}", 0, 15)
        self.display.text(f"WS: {self.connection_status}", 0, 25)
        if self.subscribed:
            self.display.text("SUBSCRIBED", 0, 35)
        self.display.text(f"Servo: {self.current_angle}°", 0, 45)
        if self.last_roll is not None:
            self.display.text(f"Roll: {self.last_roll:.1f}°", 0, 55)
        self.display.show()

    def run(self):
        """Final receiver main loop"""
        print("Starting Receiver...")
        
        while True:
            try:
                # Manage connection
                if not self.run_connection_loop():
                    time.sleep(1)
                    continue
                    
                # Update display
                current_time = time.ticks_ms()
                if time.ticks_diff(current_time, self.last_display_update) > self.display_update_interval:
                    self.update_display_status()
                    self.last_display_update = current_time
                    
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print("Main loop error:", e)
                time.sleep(5)
                
        self.close_websocket()
        self.move_servo(90)  # Center on exit

if __name__ == "__main__":
    print("="*60)
    print("ESP32 SMART MOTOR RECEIVER")
    print("="*60)
    receiver = SmartMotorReceiver()
    receiver.run()
