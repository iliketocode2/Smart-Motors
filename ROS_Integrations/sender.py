import websocket
import ssl
import json
import time

uri = "wss://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon"

class RobotController:
    def __init__(self, url):
        self.url = url
    
    def send_robot_command(self, linear_vel=0.0, angular_vel=0.0):
        # some parameters ^ and respective message:
        message = { 'topic': 'heartbeat', 'value': linear_vel }
        self._send_message(message)
    
    def move_forward(self, speed=0.5):
        self.send_robot_command(linear_vel=speed)
    
    # def move_something_else...
    
    def stop(self):
        self.send_robot_command(0.0, 0.0)
    
    def _send_message(self, message):
        ws = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_NONE})
        try:
            ws.connect(self.url)
            ws.send(json.dumps(message))
            print(f"Sent: {message}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            ws.close()

if __name__ == "__main__":
    robot = RobotController(uri)
    
    robot.move_forward(0.3)
    time.sleep(2)
    
    #...
    
    robot.stop()
