import network
import usocket as socket
import ujson
import time
import ubinascii
import sys
from machine import Pin, SoftI2C
import icons
import struct
import ussl

try:
    import ssl
except ImportError:
    ssl = None

SSID = "tufts_eecs"
PASSWORD = "foundedin1883"
WS_HOST = "chrisrogers.pyscriptapps.com"
WS_PORT = 443
WS_PATH = "/talking-on-a-channel/api/channels/hackathon"

class WebSocketBase:
    def __init__(self):
        self.display = None
        self.ws = None
        self.connection_status = "Starting"
        self.client_id = None
        self.setup_display()
        self.setup_wifi()

    def setup_display(self):
        try:
            i2c = SoftI2C(scl=Pin(7), sda=Pin(6))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 15)
            self.display.text("Starting...", 25, 45)
            self.display.show()
        except Exception as e:
            print("Display setup error:", e)
            self.display = None

    def setup_wifi(self):
        print("Connecting to WiFi...")
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        if not wlan.isconnected():
            wlan.connect(SSID, PASSWORD)
            for _ in range(30):
                if wlan.isconnected():
                    break
                print(".", end="")
                time.sleep(1)
        print("\nWiFi connected!" if wlan.isconnected() else "\nWiFi failed")

    def generate_websocket_key(self):
        import urandom
        key_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
        return ubinascii.b2a_base64(key_bytes).decode().strip()

    def connect_websocket(self):
        try:
            print("Connecting to WebSocket...")
            addr_info = socket.getaddrinfo(WS_HOST, WS_PORT)
            addr = addr_info[0][-1]
            raw_sock = socket.socket()
            raw_sock.connect(addr)
            ssl_sock = ussl.wrap_socket(raw_sock, server_hostname=WS_HOST)
            self.ws = ssl_sock

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
            
            # Read the complete HTTP response
            response = b""
            while True:
                chunk = self.ws.read(1024)
                response += chunk
                # Look for end of HTTP headers
                if b'\r\n\r\n' in response:
                    break

            print("Handshake response received")

            if b"101 Switching Protocols" in response:
                print("WebSocket connected successfully!")
                self.connection_status = "Connected"
                
                # Check if there are WebSocket frames after the HTTP headers
                header_end = response.find(b'\r\n\r\n') + 4
                if len(response) > header_end:
                    # There are WebSocket frames after the headers
                    ws_frames = response[header_end:]
                    print(f"Processing {len(ws_frames)} bytes of WebSocket frames from handshake")
                    messages = self.parse_websocket_frame(ws_frames)
                    for msg in messages:
                        self.process_channel_message(msg)
                
                return True
            else:
                self.close_websocket()
                return False
        except Exception as e:
            print("WebSocket connection error:", e)
            self.close_websocket()
            return False

    def send_websocket_frame(self, data):
        if not self.ws:
            print("WebSocket not connected.")
            return False

        try:
            import urandom
            json_data = ujson.dumps(data)
            payload = json_data.encode('utf-8')
            length = len(payload)

            frame = bytearray()
            frame.append(0x81)
            mask_key = bytearray([urandom.getrandbits(8) for _ in range(4)])
            masked_payload = bytearray(length)
            for i in range(length):
                masked_payload[i] = payload[i] ^ mask_key[i % 4]

            if length <= 125:
                frame.append(0x80 | length)
            elif length < 65536:
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

    def send_pong(self, payload=b''):
        if not self.ws:
            return
        try:
            frame = bytearray()
            frame.append(0x8A)
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
            print("Pong sent")
        except Exception as e:
            print("Pong send error:", e)
            self.close_websocket()

    def parse_websocket_frame(self, frame_data):
        i = 0
        messages = []
        
        while i < len(frame_data):
            # Check if we have enough bytes for a frame header
            if i + 2 > len(frame_data):
                # This is normal - we've reached the end of the data
                break
                
            b1 = frame_data[i]
            fin = (b1 & 0x80) >> 7
            opcode = b1 & 0x0F
            i += 1
            
            b2 = frame_data[i]
            mask = (b2 & 0x80) >> 7
            payload_len = b2 & 0x7F
            i += 1
            
            print(f"Frame: opcode={opcode}, mask={mask}, payload_len={payload_len}")
            
            # Handle extended payload length
            if payload_len == 126:
                if i + 2 > len(frame_data):
                    break
                payload_len = int.from_bytes(frame_data[i:i+2], 'big')
                i += 2
            elif payload_len == 127:
                if i + 8 > len(frame_data):
                    break
                payload_len = int.from_bytes(frame_data[i:i+8], 'big')
                i += 8
            
            # Handle masking key
            mask_key = None
            if mask:
                if i + 4 > len(frame_data):
                    break
                mask_key = frame_data[i:i+4]
                i += 4
            
            # Check if we have enough bytes for the payload
            if i + payload_len > len(frame_data):
                break
                
            # Extract and unmask payload
            payload = bytearray(frame_data[i:i+payload_len])
            i += payload_len
            
            if mask_key:
                for j in range(payload_len):
                    payload[j] ^= mask_key[j % 4]
            
            # Handle different opcodes
            if opcode == 0x1:  # Text frame
                try:
                    msg = ujson.loads(payload.decode('utf-8'))
                    messages.append(msg)
                    print("Received message:", msg)
                except Exception as e:
                    print("Text decode error:", e)
            elif opcode == 0x9:  # Ping frame
                print("Ping received - sending pong")
                self.send_pong(payload)
            elif opcode == 0x8:  # Close frame
                print("Close frame received")
                self.close_websocket()
                break
            elif opcode == 0xA:  # Pong frame
                print("Pong received")
            elif opcode == 0x0:  # Continuation frame
                print("Continuation frame received")
            else:
                print(f"Unsupported opcode: {opcode}")
        
        return messages

    def handle_incoming_messages(self):
        if not self.ws:
            return
        try:
            # Try to read data - this will block briefly if no data available
            data = self.ws.read(1024)
            if not data:
                return

            # Parse all frames in the received data
            messages = self.parse_websocket_frame(data)
            for msg in messages:
                self.process_channel_message(msg)

        except OSError as e:
            # Handle common socket errors gracefully
            if hasattr(e, 'args') and e.args[0] in (-110, 11, 9):  # ETIMEDOUT, EAGAIN, EBADF
                # These are expected when no data is available
                return
            else:
                print("WebSocket read error:", e)
                self.close_websocket()
        except Exception as e:
            print("WebSocket read error:", e)
            self.close_websocket()

    def process_channel_message(self, msg):
        pass

    def close_websocket(self):
        print("Closing WebSocket connection")
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
        self.connection_status = "Disconnected"

    def run_connection_loop(self):
        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            print("WiFi disconnected - reconnecting...")
            self.setup_wifi()
            if not wlan.isconnected():
                time.sleep(5)
                return False

        if not self.ws:
            print("Establishing WebSocket connection...")
            if not self.connect_websocket():
                time.sleep(5)
                return False

        return True

