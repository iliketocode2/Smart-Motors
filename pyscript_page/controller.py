import time
import ujson
import sys
import sensors
from websocket_base import WebSocketBase

class SmartMotorController(WebSocketBase):
    def __init__(self):
        super().__init__()
        self.sensor_system = None
        self.last_send = 0
        self.send_interval = 1000  # Send every 1 second
        self.setup_sensors()
        
        # Update display title
        if self.display:
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 15)
            self.display.text("Controller", 25, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()

    def setup_sensors(self):
        """Initialize the sensor system"""
        try:
            print("Initializing sensor system...")
            self.sensor_system = sensors.SENSORS()
        except Exception as e:
            print("Sensor setup error: {}".format(e))
            self.sensor_system = None

    def send_sensor_data(self):
        """Read sensors and send data over WebSocket"""
        if not self.sensor_system:
            return False
        try:
            x, y, z = self.sensor_system.readaccel()
            roll, pitch = self.sensor_system.readroll()
            
            # Create sensor data payload
            sensor_data = {
                "roll": round(roll, 2),
                "pitch": round(pitch, 2),
                "x": round(x, 2),
                "y": round(y, 2),
                "z": round(z, 2),
                "timestamp": time.ticks_ms(),
                "source": "controller"
            }
            
            # Send as channel message
            message = {
                "topic": "/SM/accel",
                "value": sensor_data
            }
            
            print("Sending sensor data: roll={}, pitch={}".format(roll, pitch))
            return self.send_websocket_frame(message)
        except Exception as e:
            print("Sensor read error: {}".format(e))
            print("Send failed: sensor_system =", self.sensor_system)
            return False

    def process_channel_message(self, message):
        """Process received channel messages (responses from receiver)"""
        try:
            msg_type = message.get("type", "")
            payload = message.get("payload", {})
            
            if msg_type == "message":
                topic = payload.get("topic", "")
                value = payload.get("value", "")
                
                print("Channel message - Topic: {}, Value: {}".format(topic, value))
                
                # Handle servo response from receiver
                if topic == "/SM/servo_response":
                    try:
                        response_data = ujson.loads(value) if isinstance(value, str) else value
                        servo_angle = response_data.get("servo_angle", 0)
                        received_roll = response_data.get("received_roll", 0)
                        print("Receiver confirmed: Roll={}, Servo={}".format(received_roll, servo_angle))
                    except Exception as e:
                        print("Error processing servo response: {}".format(e))
                        
        except Exception as e:
            print("Error processing channel message: {}".format(e))

    def update_display(self, wifi_status, connection_status, last_roll=None):
        """Update the controller display"""
        if not self.display:
            return
        try:
            self.display.fill(0)
            self.display.text("CONTROLLER", 20, 0)
            self.display.text("WiFi: {}".format(wifi_status), 0, 15)
            self.display.text("WS: {}".format(connection_status), 0, 25)
            if last_roll is not None:
                self.display.text("Roll: {:.1f}".format(last_roll), 0, 45)
            self.display.text("Sending...", 0, 55)
            self.display.show()
        except Exception as e:
            print("Display update error: {}".format(e))

    def run(self):
        """Final controller main loop"""
        print("Starting Controller...")
        last_roll = None
        
        while True:
            try:
                # Manage connection
#                 if not self.run_connection_loop():
#                     time.sleep(1)
#                     continue
# 
#                 self.handle_incoming_messages()
                try:
                    data = self.ws.read(1024)
                    if data:
                        print("Got raw WebSocket data:", repr(data))
                        self.parse_websocket_frame(data)
                except Exception as e:
                    print("WebSocket read error:", e)


                self.send_sensor_data()  # Or receiver logic
                time.sleep(0.2)

                
#                 if self.subscribe_to_channel():
#                     print("Subscribed to channel successfully.")
#                 else:
#                     print("Subscription failed.")

                    
                # Send sensor data
#                 current_time = time.ticks_ms()
#                 if time.ticks_diff(current_time, self.last_send) > self.send_interval:
#                     if self.send_sensor_data():
#                         self.last_send = current_time
#                         try:
#                             if self.sensor_system:
#                                 _, roll = self.sensor_system.readroll()
#                                 last_roll = roll
#                         except:
#                             pass
#                     else:
#                         print("Failed to send sensor data")
#                         time.sleep(1)
#                         
#                 time.sleep(0.1)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print("Main loop error:", e)
                time.sleep(5)
                
        self.close_websocket()

if __name__ == "__main__":
    print("="*60)
    print("ESP32 SMART MOTOR CONTROLLER")
    print("="*60)
    controller = SmartMotorController()
    controller.run()
