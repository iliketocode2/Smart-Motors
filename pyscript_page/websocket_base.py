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
import ussl
 
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
        """Establish WebSocket connection with improved error handling"""
        try:
            print("Connecting to WebSocket...")
            
            # Create raw socket
            addr_info = socket.getaddrinfo(WS_HOST, WS_PORT)
            addr = addr_info[0][-1]
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(20)  # 20 second timeout
            
            # Connect and wrap with SSL
            sock.connect(addr)
            if ssl:
                self.ws = ussl.wrap_socket(sock, server_hostname=WS_HOST)
            else:
                self.ws = sock
            
            # Generate WebSocket key
            ws_key = self.generate_websocket_key()
            
            # Send handshake
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
            
            # Read response
            response = self.ws.read(1024)
            print("Handshake response:", response)
            
            if b"101 Switching Protocols" in response:
                print("WebSocket connected successfully!")
                self.connection_status = "Connected"
                return True
            else:
                print("WebSocket handshake failed")
                self.close_websocket()
                return False
                
        except Exception as e:
            print("WebSocket connection error:", e)
            self.close_websocket()
            return False

    def parse_websocket_frame(self, frame_data):
        """Improved WebSocket frame parser"""
        messages = []
        i = 0
        
        while i < len(frame_data):
            if i + 1 >= len(frame_data):
                break
                
            # Parse frame header
            first_byte = frame_data[i]
            fin = (first_byte & 0x80) != 0
            opcode = first_byte & 0x0F
            i += 1
            
            second_byte = frame_data[i]
            masked = (second_byte & 0x80) != 0
            payload_len = second_byte & 0x7F
            i += 1
            
            # Handle extended payload length
            if payload_len == 126:
                if i + 2 > len(frame_data):
                    break
                payload_len = (frame_data[i] << 8) + frame_data[i+1]
                i += 2
            elif payload_len == 127:
                if i + 8 > len(frame_data):
                    break
                payload_len = 0
                for j in range(8):
                    payload_len = (payload_len << 8) + frame_data[i+j]
                i += 8
            
            # Skip mask if present (shouldn't be from server)
            if masked and i + 4 <= len(frame_data):
                mask_key = frame_data[i:i+4]
                i += 4
            else:
                mask_key = None
            
            # Handle different opcodes
            if opcode == 0x1:  # Text frame
                if i + payload_len > len(frame_data):
                    break
                    
                payload = frame_data[i:i+payload_len]
                i += payload_len
                
                # Unmask if needed
                if mask_key:
                    payload = bytearray(payload)
                    for j in range(len(payload)):
                        payload[j] ^= mask_key[j % 4]
                
                try:
                    message = ujson.loads(payload.decode('utf-8'))
                    messages.append(message)
                    if "client_id" in message:
                        self.client_id = message["client_id"]
                except Exception as e:
                    print("JSON decode error:", e)
                    
            elif opcode == 0x8:  # Close frame
                print("Close frame received")
                self.close_websocket()
                break
                
            elif opcode == 0x9:  # Ping frame
                print("Ping received - sending pong")
                self.send_pong(frame_data[i:i+payload_len])
                i += payload_len
                
            elif opcode == 0xA:  # Pong frame
                print("Pong received")
                i += payload_len
                
            else:
                print(f"Unknown opcode: {opcode} - skipping")
                i += payload_len
                
        return messages

    def send_pong(self, payload=None):
        """Send pong response to ping"""
        if not self.ws:
            return
            
        try:
            frame = bytearray([0x8A])  # Pong opcode
            if payload:
                frame.append(len(payload))
                frame.extend(payload)
            else:
                frame.append(0)
            self.ws.write(frame)
        except Exception as e:
            print("Pong send error:", e)
            self.close_websocket()

    def send_websocket_frame(self, data):
        """Improved WebSocket frame sending"""
        if not self.ws:
            return False
            
        try:
            # Convert data to JSON
            json_data = ujson.dumps(data)
            payload = json_data.encode('utf-8')
            length = len(payload)
            
            # Build WebSocket frame
            frame = bytearray()
            frame.append(0x81)  # FIN + text frame
            
            if length <= 125:
                frame.append(length)
            elif length <= 65535:
                frame.append(126)
                frame.extend(length.to_bytes(2, 'big'))
            else:
                frame.append(127)
                frame.extend(length.to_bytes(8, 'big'))
            
            frame.extend(payload)
            
            # Send frame
            self.ws.write(frame)
            return True
            
        except Exception as e:
            print("WebSocket send error:", e)
            self.close_websocket()
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
        """Improved message handler"""
        try:
            if not self.ws:
                return
                
            poll = uselect.poll()
            poll.register(self.ws, uselect.POLLIN)
            events = poll.poll(50)  # 50ms timeout
            
            if events:
                data = self.ws.read(1024)
                if not data:
                    print("Connection closed by server")
                    self.close_websocket()
                    return
                    
                messages = self.parse_websocket_frame(data)
                for msg in messages:
                    self.process_channel_message(msg)
                    
        except Exception as e:
            print("Message handling error:", e)
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
        """Improved connection management"""
        import network
        wlan = network.WLAN(network.STA_IF)
        
        # Check WiFi
        if not wlan.isconnected():
            print("WiFi disconnected - reconnecting...")
            self.setup_wifi()
            if not wlan.isconnected():
                time.sleep(5)
                return False
                
        # Check WebSocket
        if not self.ws:
            print("Establishing WebSocket connection...")
            if not self.connect_websocket():
                time.sleep(5)
                return False
                
        # Handle incoming messages
        try:
            poll = uselect.poll()
            poll.register(self.ws, uselect.POLLIN)
            events = poll.poll(50)  # 50ms timeout
            
            if events:
                data = self.ws.read(1024)
                if data:
                    self.parse_websocket_frame(data)
                else:
                    print("Connection closed by server")
                    self.close_websocket()
                    return False
                    
        except Exception as e:
            print("Connection error:", e)
            self.close_websocket()
            return False
            
        return True
