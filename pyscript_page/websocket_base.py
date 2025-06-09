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
import urandom
 
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
                time.sleep(0.5)
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
        """Parse incoming WebSocket frames (RFC 6455)"""
        i = 0
        messages = []

        while i < len(frame_data):
            if i + 2 > len(frame_data):
                break  # incomplete frame

            b1 = frame_data[i]
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            i += 1

            b2 = frame_data[i]
            mask = b2 & 0x80
            payload_len = b2 & 0x7F
            i += 1

            if payload_len == 126:
                if i + 2 > len(frame_data): break
                payload_len = (frame_data[i] << 8) + frame_data[i + 1]
                i += 2
            elif payload_len == 127:
                if i + 8 > len(frame_data): break
                payload_len = int.from_bytes(frame_data[i:i+8], 'big')
                i += 8

            if mask:
                if i + 4 > len(frame_data): break
                mask_key = frame_data[i:i+4]
                i += 4
            else:
                mask_key = None

            if i + payload_len > len(frame_data):
                break  # wait for more data

            payload = bytearray(frame_data[i:i + payload_len])
            i += payload_len

            if mask_key:
                for j in range(payload_len):
                    payload[j] ^= mask_key[j % 4]

            # Handle opcodes
            if opcode == 0x1:  # text
                try:
                    msg = ujson.loads(payload.decode('utf-8'))
                    messages.append(msg)
                except Exception as e:
                    print("Text decode error:", e)
            elif opcode == 0x8:  # close
                print("Close frame received")
                self.close_websocket()
                break
            elif opcode == 0x9:  # Ping
                print(f"Ping received! Payload: {repr(payload)}")
                self.send_pong(payload)
            elif opcode == 0xA:  # pong
                print("Pong received")
            else:
                print(f"Unsupported opcode: {opcode} - skipping {payload_len} bytes")

        return messages


    def send_pong(self, payload=b''):
        """Send Pong frame in response to Ping"""
        if not self.ws:
            return

        try:
            frame = bytearray()
            frame.append(0x8A)  # FIN + opcode 0xA (pong)

            length = len(payload)
            if length <= 125:
                frame.append(length)
            elif length < 65536:
                frame.append(126)
                frame.extend(length.to_bytes(2, 'big'))
            else:
                frame.append(127)
                frame.extend(length.to_bytes(8, 'big'))

            frame.extend(payload)
            self.ws.write(frame)
            time.sleep(0.01)

            print("Pong sent")
        except Exception as e:
            print("Pong send error:", e)
            self.close_websocket()
            

    def handle_incoming_messages(self):
        """Read and respond to incoming WebSocket messages (ping, data, etc.)"""
        try:
            if not self.ws:
                return

            import uselect
            poll = uselect.poll()
            poll.register(self.ws, uselect.POLLIN)
            events = poll.poll(10)  # small timeout

            if events:
                data = self.ws.read(1024)
                if not data:
                    print("Server closed the connection")
                    self.close_websocket()
                    return

                messages = self.parse_websocket_frame(data)
                for msg in messages:
                    self.process_channel_message(msg)

        except Exception as e:
            print("Message handling error:", e)
            self.close_websocket()


    def send_websocket_frame(self, data):
        """Send WebSocket text frame with masking (RFC 6455 compliant)"""
        if not self.ws:
            return False

        try:
            import urandom

            # JSON encode and convert to bytes
            json_data = ujson.dumps(data)
            payload = json_data.encode('utf-8')
            length = len(payload)

            frame = bytearray()
            frame.append(0x81)  # FIN bit + text frame opcode

            # Use client-to-server masking (required)
            mask_key = bytearray([urandom.getrandbits(8) for _ in range(4)])
            masked_payload = bytearray(length)

            for i in range(length):
                masked_payload[i] = payload[i] ^ mask_key[i % 4]

            # Determine length format
            if length <= 125:
                frame.append(0x80 | length)  # Mask bit set
            elif length < (1 << 16):
                frame.append(0x80 | 126)
                frame.extend(length.to_bytes(2, 'big'))
            else:
                frame.append(0x80 | 127)
                frame.extend(length.to_bytes(8, 'big'))

            frame.extend(mask_key)
            frame.extend(masked_payload)

            self.ws.write(frame)
            return True

        except Exception as e:
            print("WebSocket send error:", e)
            self.close_websocket()
            return False
        

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
                print("Server sent before disconnect:", repr(data))
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
