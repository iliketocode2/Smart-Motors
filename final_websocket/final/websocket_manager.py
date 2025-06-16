"""
WebSocket connection manager optimized for stability
Handles connection, message framing, and error recovery
"""

import socket
import ussl
import json
import time
import ubinascii
import urandom
import gc
import config

class WebSocketManager:
    def __init__(self, hardware_manager=None):
        """Initialize WebSocket manager - back to original simple approach"""
        self.hardware_manager = hardware_manager
        self.socket = None
        self.connected = False
        self.receive_buffer = bytearray()
        self.connection_attempts = 0
        self.last_activity = time.ticks_ms()
        
    def generate_websocket_key(self):
        """Generate WebSocket key exactly like original"""
        key_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
        return ubinascii.b2a_base64(key_bytes).decode().strip()
    
    def connect(self):
        """Establish WebSocket connection using original working logic"""
        try:
            if self.hardware_manager:
                self.hardware_manager.update_display("SmartMotor", "WebSocket", "Connecting...", "")
            
            print("Connecting to WebSocket...")
            
            # Clean up any existing connection
            self._cleanup_socket()
            
            # Reset connection state
            self.connection_attempts = 0
            self.last_activity = time.ticks_ms()
            
            # Resolve address - exactly like original
            addr_info = socket.getaddrinfo(config.WS_HOST, config.WS_PORT)
            addr = addr_info[0][-1]
            
            # Create SSL socket - exactly like original
            raw_sock = socket.socket()
            raw_sock.settimeout(10)  # Set timeout for connection
            raw_sock.connect(addr)
            self.socket = ussl.wrap_socket(raw_sock, server_hostname=config.WS_HOST)
            
            # WebSocket handshake - exactly like original
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
            ).format(config.WS_PATH, config.WS_HOST, ws_key)
            
            self.socket.write(handshake.encode())
            
            # Read handshake response - exactly like original
            response = b""
            while b'\r\n\r\n' not in response:
                chunk = self.socket.read(1024)
                if not chunk:
                    break
                response += chunk
            
            if b"101 Switching Protocols" in response:
                print("WebSocket connected successfully!")
                if self.hardware_manager:
                    self.hardware_manager.update_display("SmartMotor", "Connected", "Ready", "")
                self.connected = True
                self.receive_buffer = bytearray()  # Clear buffer
                
                # Initialize timing
                current_time = time.ticks_ms()
                self.last_activity = current_time
                
                # Force garbage collection
                gc.collect()
                return True
            else:
                print("WebSocket handshake failed")
                if self.hardware_manager:
                    self.hardware_manager.update_display("SmartMotor", "WS Failed", "Handshake", "")
                return False
                
        except Exception as e:
            print("WebSocket connection error: {}".format(e))
            if self.hardware_manager:
                error_str = str(e)[:12]
                self.hardware_manager.update_display("SmartMotor", "WS Error", error_str, "")
            return False
    
    def send_message(self, message_dict):
        """Send JSON message using original framing logic"""
        if not self.connected:
            return False
        
        try:
            # Convert to JSON and encode - exactly like original
            json_data = json.dumps(message_dict)
            payload = json_data.encode('utf-8')
            length = len(payload)
            
            # Limit message size
            if length > config.MAX_MESSAGE_SIZE:
                print("Message too large, skipping")
                return False
            
            # Create WebSocket frame - exactly like original
            frame = bytearray()
            frame.append(0x81)  # FIN=1, opcode=1 (text)
            
            # Generate mask key - exactly like original
            mask_key = bytearray([urandom.getrandbits(8) for _ in range(4)])
            
            # Add length and mask bit - exactly like original
            if length <= 125:
                frame.append(0x80 | length)
            elif length < 65536:
                frame.append(0x80 | 126)
                frame.extend(length.to_bytes(2, 'big'))
            else:
                return False  # Message too large
            
            # Add mask key
            frame.extend(mask_key)
            
            # Mask and add payload - exactly like original
            for i in range(length):
                frame.append(payload[i] ^ mask_key[i % 4])
            
            # Send with error handling
            self.socket.write(frame)
            self.last_activity = time.ticks_ms()
            
            return True
            
        except Exception as e:
            print("Send message error: {}".format(e))
            self.connected = False
            return False
    
    def receive_messages(self):
        """Receive messages - exactly like original draft2.py"""
        if not self.connected:
            return []
        
        try:
            # Try to read data
            data = self.socket.read(config.RECEIVE_CHUNK_SIZE)
            if data:
                # Add to buffer
                self.receive_buffer.extend(data)
                
                # Prevent buffer overflow
                if len(self.receive_buffer) > config.MAX_BUFFER_SIZE:
                    # Keep only the last part
                    self.receive_buffer = self.receive_buffer[-config.RECEIVE_CHUNK_SIZE:]
                
                # Process complete messages
                messages = self.extract_json_messages(self.receive_buffer)
                for message in messages:
                    print("Received message: {}".format(message[:100]))
                return messages
                
        except OSError as e:
            # Normal timeout - continue
            pass
        except Exception as e:
            print("Read error: {}".format(e))
            self.connected = False
        
        return []
    
    def safe_decode(self, data):
        """Safely decode bytes to string - from original draft2.py"""
        try:
            if isinstance(data, bytes):
                return data.decode('utf-8', 'ignore')
            elif isinstance(data, bytearray):
                return bytes(data).decode('utf-8', 'ignore')
            else:
                return str(data)
        except:
            return ""
    
    def extract_json_messages(self, buffer):
        """Extract JSON messages - EXACT copy from original draft2.py"""
        messages = []
        
        try:
            text = self.safe_decode(buffer)
            if not text:
                return messages
            
            start = 0
            while start < len(text):
                # Find start of JSON object
                json_start = text.find('{', start)
                if json_start == -1:
                    break
                
                # Find matching closing brace
                brace_count = 0
                json_end = -1
                
                for i in range(json_start, len(text)):
                    if text[i] == '{':
                        brace_count += 1
                    elif text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break
                
                if json_end != -1:
                    json_str = text[json_start:json_end]
                    messages.append(json_str)
                    start = json_end
                else:
                    # Incomplete JSON - keep remaining for next time
                    remaining = text[json_start:].encode('utf-8')
                    self.receive_buffer = bytearray(remaining)
                    break
            
            # If we processed everything, clear the buffer
            if start >= len(text):
                self.receive_buffer = bytearray()
            
        except Exception as e:
            print("Message extraction error: {}".format(e))
            # Clear corrupted buffer
            self.receive_buffer = bytearray()
        
        return messages
    
    def is_connected(self):
        """Check if connection is still active"""
        if not self.connected:
            return False
        
        # Check for timeout
        if time.ticks_diff(time.ticks_ms(), self.last_activity) > config.MESSAGE_TIMEOUT_MS:
            print("Connection timeout detected")
            self.connected = False
            return False
        
        return True
    
    def _cleanup_socket(self):
        """Clean up socket resources"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        self.connected = False
        self.receive_buffer = bytearray()
        gc.collect()
    
    def close(self):
        """Close WebSocket connection"""
        print("Closing WebSocket connection")
        self._cleanup_socket()
