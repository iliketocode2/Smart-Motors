import network
import usocket as socket
import ujson
import time
import ubinascii
import sys
from machine import Pin, SoftI2C
import icons
import uselect
import struct

try:
    import ssl
except ImportError:
    ssl = None

# Shared configuration
SSID = "tufts_eecs"
PASSWORD = ""
WS_HOST = "chrisrogers.pyscriptapps.com"
WS_PORT = 443
WS_PATH = "/talking-on-a-channel/api/channels/hackathon"

class WebSocketBase:
    """Base class for WebSocket communication functionality"""
    
    def __init__(self):
        self.display = None
        self.ws = None
        self.connection_status = "Starting"
        self.subscribed = False
        self.client_id = None
        self.setup_display()
        self.setup_wifi()

    def setup_display(self):
        """Initialize the OLED display"""
        try:
            i2c = SoftI2C(scl=Pin(7), sda=Pin(6))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 15)
            self.display.text("Starting...", 25, 45)
            self.display.show()
        except Exception as e:
            print("Display setup error: {}".format(e))
            self.display = None

    def setup_wifi(self):
        """Connect to WiFi network"""
        print("Connecting to WiFi...")
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        if not wlan.isconnected():
            if self.display:
                self.display.fill(0)
                self.display.text("Connecting WiFi", 10, 20)
                self.display.text(SSID[:16], 10, 35)
                self.display.show()
            
            wlan.connect(SSID, PASSWORD)
            for _ in range(30):
                if wlan.isconnected():
                    break
                print(".", end="")
                time.sleep(1)
            
            print("\nWiFi connected!" if wlan.isconnected() else "\nWiFi failed")
            
            if wlan.isconnected():
                ip = wlan.ifconfig()[0]
                if self.display:
                    self.display.fill(0)
                    self.display.text("WiFi Connected", 10, 20)
                    self.display.text(ip, 10, 35)
                    self.display.show()
                time.sleep(2)

    def generate_websocket_key(self):
        """Generate WebSocket key for handshake"""
        import urandom
        key_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
        return ubinascii.b2a_base64(key_bytes).decode().strip()

    def connect_websocket(self):
        """Establish WebSocket connection"""
        try:
            print("Connecting to WebSocket: wss://{}{}".format(WS_HOST, WS_PATH))
            raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_socket.settimeout(10)
            addr_info = socket.getaddrinfo(WS_HOST, WS_PORT)
            addr = addr_info[0][-1]
            raw_socket.connect(addr)
            self.ws = ssl.wrap_socket(raw_socket, server_hostname=WS_HOST)

            ws_key = self.generate_websocket_key()
            handshake = (
                "GET {} HTTP/1.1\r\n"
                "Host: {}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: {}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Origin: https://esp32-device\r\n"
                "\r\n"
            ).format(WS_PATH, WS_HOST, ws_key)

            self.ws.write(handshake.encode())
            response = self.ws.read(1024)
            print("HANDSHAKE RESPONSE: {}".format(response))

            if response and b"101 Switching Protocols" in response:
                print("WebSocket connected!")
                self.connection_status = "Connected"
                self.subscribed = False
                self.client_id = None
                return True
            else:
                print("Handshake failed")
                self.ws.close()
                self.ws = None
                self.connection_status = "Handshake Failed"
                return False
        except Exception as e:
            sys.print_exception(e)
            print("WebSocket connection error: {}".format(repr(e)))
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
            self.ws = None
            self.connection_status = "Connection Error"
            return False

    def parse_websocket_frame(self, frame_data):
        """Parse WebSocket frame data and extract messages"""
        messages = []
        i = 0
        
        print("Raw frame data length: {}, data: {}".format(len(frame_data), frame_data))
        
        while i < len(frame_data):
            if i + 1 >= len(frame_data):
                break
                
            # Get first byte
            first_byte = frame_data[i]
            fin = (first_byte & 0x80) != 0
            opcode = first_byte & 0x0F
            
            print("Frame at {}: FIN={}, opcode={}".format(i, fin, opcode))
            
            i += 1
            if i >= len(frame_data):
                break
                
            # Get second byte
            second_byte = frame_data[i]
            masked = (second_byte & 0x80) != 0
            payload_len = second_byte & 0x7F
            
            print("Payload length indicator: {}, masked: {}".format(payload_len, masked))
            
            i += 1
            
            # Determine actual payload length
            if payload_len < 126:
                length = payload_len
            elif payload_len == 126:
                if i + 2 > len(frame_data):
                    print("Not enough data for extended length")
                    break
                length = struct.unpack('>H', frame_data[i:i+2])[0]
                i += 2
            elif payload_len == 127:
                if i + 8 > len(frame_data):
                    print("Not enough data for extended length")
                    break
                length = struct.unpack('>Q', frame_data[i:i+8])[0]
                i += 8
            else:
                print("Invalid payload length")
                break
                
            print("Actual payload length: {}".format(length))
            
            # Skip mask key if present (server-to-client frames shouldn't be masked)
            if masked:
                if i + 4 > len(frame_data):
                    print("Not enough data for mask")
                    break
                mask_key = frame_data[i:i+4]
                i += 4
                print("Mask key: {}".format(mask_key))
            
            # Handle different frame types
            if opcode == 1:  # Text frame
                if i + length > len(frame_data):
                    print("Not enough data for payload")
                    break
                    
                payload_bytes = frame_data[i:i+length]
                
                # Unmask if needed
                if masked:
                    payload_bytes = bytearray(payload_bytes)
                    for j in range(len(payload_bytes)):
                        payload_bytes[j] ^= mask_key[j % 4]
                
                try:
                    payload = payload_bytes.decode('utf-8')
                    print("Decoded payload: {}".format(payload))
                    json_msg = ujson.loads(payload)
                    messages.append(json_msg)
                    print("Parsed JSON: {}".format(json_msg))
                    
                    # Handle client_id assignment
                    if "client_id" in json_msg:
                        self.client_id = json_msg["client_id"]
                        print("Assigned client_id: {}".format(self.client_id))
                        
                except Exception as e:
                    print("JSON parse error: {}".format(e))
                    print("Raw payload: {}".format(payload_bytes))
                    
            elif opcode == 8:  # Close frame
                print("Received close frame")
                if i + length <= len(frame_data):
                    close_payload = frame_data[i:i+length]
                    if len(close_payload) >= 2:
                        close_code = struct.unpack('>H', close_payload[:2])[0]
                        close_reason = close_payload[2:].decode('utf-8', errors='ignore')
                        print("Close code: {}, reason: {}".format(close_code, close_reason))
                return messages
                
            elif opcode == 9:  # Ping frame
                print("Received ping frame")
                
            elif opcode == 10:  # Pong frame
                print("Received pong frame")
                
            else:
                print("Unknown opcode: {}".format(opcode))
                
            i += length
            
        return messages

    def send_websocket_frame(self, data):
        """Send data as WebSocket frame"""
        if not self.ws:
            return False
        try:
            json_data = ujson.dumps(data)
            payload = json_data.encode("utf-8")
            length = len(payload)
            print("Sending: {}".format(json_data))

            frame = bytearray()
            frame.append(0x81)  # Text frame, FIN=1
            if length < 126:
                frame.append(length)
            elif length < 65536:
                frame.append(126)
                frame.extend(length.to_bytes(2, 'big'))
            else:
                frame.append(127)
                frame.extend(length.to_bytes(8, 'big'))

            frame.extend(payload)
            self.ws.write(frame)
            return True
        except Exception as e:
            sys.print_exception(e)
            print("WebSocket send error: {}".format(e))
            self.connection_status = "Send Error"
            try:
                if self.ws:
                    self.ws.close()
            except:
                pass
            self.ws = None
            return False

    def subscribe_to_channel(self):
        """Subscribe to channel with retry logic"""
        if self.subscribed:
            return True
            
        max_retries = 3
        for attempt in range(max_retries):
            try:
                subscribe_msg = {
                    "type": "subscribe",
                    "payload": ""
                }
                
                print("Subscription attempt {} of {}".format(attempt + 1, max_retries))
                
                if self.send_websocket_frame(subscribe_msg):
                    print("Subscribe message sent successfully")
                    
                    # Wait for confirmation with timeout
                    start_time = time.ticks_ms()
                    timeout = 5000  # 5 seconds
                    
                    while time.ticks_diff(time.ticks_ms(), start_time) < timeout:
                        self.handle_incoming_messages()
                        
                        # Check if we received any messages indicating success
                        if self.client_id:
                            print("Subscription successful - client_id received: {}".format(self.client_id))
                            self.subscribed = True
                            return True
                            
                        time.sleep(0.1)
                    
                    print("Subscription timeout on attempt {}".format(attempt + 1))
                    
                else:
                    print("Failed to send subscribe message on attempt {}".format(attempt + 1))
                    
            except Exception as e:
                print("Subscription error on attempt {}: {}".format(attempt + 1, e))
                
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retry
        
        print("All subscription attempts failed")
        return False

    def handle_incoming_messages(self):
        """Handle incoming WebSocket messages"""
        try:
            if not self.ws:
                return
                
            # Use non-blocking socket check
            poll = uselect.poll()
            poll.register(self.ws, uselect.POLLIN)
            events = poll.poll(50)  # 50ms timeout
            
            if events:
                try:
                    # Read available data
                    data = self.ws.read(2048)  # Increased buffer size
                    if not data:
                        print("No data received - connection closed")
                        self.close_websocket()
                        return
                        
                    print("Received {} bytes".format(len(data)))
                    
                    # Parse all messages in the frame
                    messages = self.parse_websocket_frame(data)
                    
                    # Process each message
                    for msg in messages:
                        print("Processing message: {}".format(msg))
                        
                        # Handle different message types
                        msg_type = msg.get("type", "")
                        
                        if msg_type == "message":
                            # This is a channel message - override in subclass
                            self.process_channel_message(msg)
                        elif msg_type == "subscribe":
                            print("Received subscribe confirmation")
                        elif msg_type == "unsubscribe":
                            print("Received unsubscribe notification")
                        else:
                            print("Unknown message type: {}".format(msg_type))
                            
                except OSError as e:
                    if e.args[0] == -116:  # ETIMEDOUT
                        # This is normal - no data available
                        pass
                    else:
                        print("Socket error: {}".format(e))
                        self.close_websocket()
                except Exception as e:
                    print("Message handling error: {}".format(e))
                    # Don't close connection for parsing errors
                    
        except Exception as e:
            print("Critical message handler error: {}".format(e))
            self.close_websocket()

    def process_channel_message(self, message):
        """Process channel message - override in subclass"""
        pass

    def close_websocket(self):
        """Properly close WebSocket connection"""
        print("Closing WebSocket connection")
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
        self.subscribed = False
        self.client_id = None
        self.connection_status = "Disconnected"

    def wait_for_connection_ready(self):
        """Wait for WebSocket to be fully ready"""
        print("Waiting for connection to be ready...")
        start_time = time.ticks_ms()
        timeout = 10000  # 10 seconds
        
        while time.ticks_diff(time.ticks_ms(), start_time) < timeout:
            try:
                # Process any incoming messages
                self.handle_incoming_messages()
                
                # Send a small test frame to verify connection
                test_msg = {
                    "type": "ping",
                    "payload": "connection_test"
                }
                
                if self.send_websocket_frame(test_msg):
                    print("Connection test successful")
                    return True
                else:
                    print("Connection test failed")
                    return False
                    
            except Exception as e:
                print("Connection readiness check error: {}".format(e))
                return False
                
            time.sleep(0.5)
        
        print("Connection readiness timeout")
        return False

    def run_connection_loop(self):
        """Main connection management loop - call from subclass run() method"""
        wlan = network.WLAN(network.STA_IF)
        connection_retry_delay = 5
        max_connection_retries = 3
        connection_attempts = 0
        
        # Check WiFi connection
        if not wlan.isconnected():
            print("WiFi disconnected. Reconnecting...")
            self.setup_wifi()
            if not wlan.isconnected():
                time.sleep(connection_retry_delay)
                return False
            connection_attempts = 0  # Reset on successful WiFi
                
        # Check WebSocket connection
        if not self.ws:
            print("WebSocket not connected. Attempting connection...")
            connection_attempts += 1
            
            if connection_attempts > max_connection_retries:
                print("Max connection attempts reached. Waiting longer...")
                time.sleep(connection_retry_delay * 3)
                connection_attempts = 0
                return False
            
            if self.connect_websocket():
                print("WebSocket connected successfully")
                
                # Wait for connection to stabilize
                if self.wait_for_connection_ready():
                    print("Connection is ready")
                    
                    # Subscribe to channel
                    if self.subscribe_to_channel():
                        print("Successfully subscribed to channel")
                        connection_attempts = 0  # Reset on success
                        return True
                    else:
                        print("Failed to subscribe to channel")
                        self.close_websocket()
                        time.sleep(connection_retry_delay)
                        return False
                else:
                    print("Connection not ready")
                    self.close_websocket()
                    time.sleep(connection_retry_delay)
                    return False
            else:
                print("WebSocket connection failed")
                time.sleep(connection_retry_delay)
                return False
        
        # Process incoming messages
        self.handle_incoming_messages()
        return True
