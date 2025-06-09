import time
import ujson
import sensors
from websocket_base import WebSocketBase

class SmartMotorController(WebSocketBase):
    def __init__(self):
        super().__init__()
        self.sensor_system = None
        self.last_send = 0
        self.send_interval = 5000
        self.setup_sensors()

        if self.display:
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 15)
            self.display.text("Controller", 25, 25)
            self.display.text("Starting...", 25, 45)
            self.display.show()

    def setup_sensors(self):
        try:
            print("Initializing sensor system...")
            self.sensor_system = sensors.SENSORS()
        except Exception as e:
            print("Sensor setup error:", e)
            self.sensor_system = None

    def send_sensor_data(self):
        if not self.sensor_system:
            return False
        try:
            x, y, z = self.sensor_system.readaccel()
            roll, pitch = self.sensor_system.readroll()

            sensor_data = {
                "roll": round(roll, 2),
                "pitch": round(pitch, 2),
                "x": round(x, 2),
                "y": round(y, 2),
                "z": round(z, 2),
                "timestamp": time.ticks_ms(),
                "source": "controller"
            }

            message = {
                "topic": "/SM/accel",
                "value": sensor_data
            }

            print("Sending sensor data: roll={}, pitch={}".format(roll, pitch))
            return self.send_websocket_frame(message)
        except Exception as e:
            print("Sensor read error:", e)
            return False

    def process_channel_message(self, message):
        try:
            msg_type = message.get("type", "")
            payload = message.get("payload", {})
            if msg_type == "data":
                topic = payload.get("topic", "")
                value = payload.get("value", {})
                print("Received on topic '{}': {}".format(topic, value))
        except Exception as e:
            print("Error processing channel message:", e)

    def run(self):
        print("Starting Controller...")
        while True:
            try:
                if not self.run_connection_loop():
                    time.sleep(1)
                    continue

                self.handle_incoming_messages()

                current_time = time.ticks_ms()
                if time.ticks_diff(current_time, self.last_send) > self.send_interval:
                    if self.send_sensor_data():
                        self.last_send = current_time

                time.sleep(0.1)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print("Main loop error:", e)
                time.sleep(5)

        self.close_websocket()

if __name__ == "__main__":
    print("=" * 60)
    print("ESP32 SMART MOTOR CONTROLLER")
    print("=" * 60)
    controller = SmartMotorController()
    controller.run()

