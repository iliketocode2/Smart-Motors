import asyncio
import websockets
import ssl
import json
import threading
import queue
import rospy
from std_msgs.msg import String
from geometry_msgs.msg import Twist

class WebSocketRosBridge:
    def __init__(self, websocket_uri):
        self.websocket_uri = websocket_uri
        self.message_queue = queue.Queue()
        self.running = False
        
        if not rospy.core.is_initialized():
            rospy.init_node('websocket_bridge', anonymous=True, disable_signals=True)
        
        self.cmd_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
        self.data_pub = rospy.Publisher('/websocket_data', String, queue_size=10)
    
    def websocket_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._websocket_listener())
    
    async def _websocket_listener(self):
        try:
            async with websockets.connect(self.websocket_uri, ssl=True) as websocket:
                while self.running:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        self.message_queue.put(data)
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            print(f"WebSocket error: {e}")
    
    def ros_thread(self):
        rate = rospy.Rate(10)
        while self.running and not rospy.is_shutdown():
            try:
                data = self.message_queue.get(timeout=0.1)
                self._process_message(data)
            except queue.Empty:
                pass
            rate.sleep()
    
    def _process_message(self, data):
        if data.get('type') == 'data' and data.get('payload'):
            try:
                payload = json.loads(data['payload'])
                
                if 'cmd_vel' in payload:
                    # do something
                    self.cmd_pub.publish(cmd)
                
                self.data_pub.publish(String(data=json.dumps(payload)))
                
            except json.JSONDecodeError:
                pass
    
    def start(self):
        self.running = True
        
        self.ws_thread = threading.Thread(target=self.websocket_thread, daemon=True)
        self.ros_thread = threading.Thread(target=self.ros_thread, daemon=True)
        
        self.ws_thread.start()
        self.ros_thread.start()
        
        return self.ws_thread, self.ros_thread
    
    def stop(self):
        self.running = False
        
        if hasattr(self, 'ws_thread') and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2)
        if hasattr(self, 'ros_thread') and self.ros_thread.is_alive():
            self.ros_thread.join(timeout=2)

# Usage in Jupyter cell:
bridge = WebSocketRosBridge("wss://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon")
ws_thread, ros_thread = bridge.start()

# bridge.stop()
