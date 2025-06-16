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
        """Initialize WebSocket manager with improved stability"""
        self.hardware_manager = hardware_manager
        self.socket = None
        self.connected = False
        self.receive_buffer = bytearray()
        self.connection_attempts = 0
        self.last_activity = 0
        
    def connect(self):
        """Establish WebSocket connection with improved handshake"""
        try:
            if self.hardware_manager:
                self.hardware_manager.update_display("SmartMotor", "WebSocket", "Connecting...", "")
            
            print("Establishing WebSocket connection...")
            
            # Clean up any existing connection
            self._cleanup_socket()
            
            # Resolve host address
            addr_info = socket.getaddrinfo(config.WS_HOST, config.WS_PORT)
            if not addr_info:
                raise Exception("Failed to resolve host")
            
            addr = addr_info[0][-1]
            
            # Create and configure raw socket
            raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_socket.settimeout(15)  # Longer timeout for initial connection
            
            # Connect to server
            raw_socket.connect(addr)
            
            # Wrap with SSL
            self.socket = ussl.wrap_socket(raw_socket, server_hostname=config.WS_HOST)
            
            # Perform WebSocket handshake
            if self._perform_handshake():
                self.connected = True
                self.last_activity = time.ticks_ms()
                self.receive_buffer = bytearray()
                self.connection_attempts = 0
                
                print("WebSocket connected successfully")
                if self.hardware_manager:
                    self.hardware_manager.update_display("SmartMotor", "Connected", "WebSocket OK", "")
                
                # Force garbage collection after connection
                gc.collect()
                return True
            else:
                self._cleanup_socket()
                return False
                
        except Exception as e:
            print(f"WebSocket connection failed: {e}")
            if self.hardware_manager:
                error_short = str(e)[:12]
                self.hardware_manager.update_display("SmartMotor", "WS Failed", error_short, "")
            
            self._cleanup_socket()
            return False
    
    def _perform_handshake(self):
        """Perform WebSocket handshake with proper error handling"""
        try:
            # Generate WebSocket key
            key_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
            ws_key = ubinascii.b2a_base64(key_bytes).decode().strip()
            
            # Create handshake request
            handshake_request = (
                f"GET {config.WS_PATH} HTTP/1.1\r\n"
                f"Host: {config.WS_HOST}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {ws_key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "Origin: https://esp32-smartmotor\r\n"
                "User-Agent: ESP32-SmartMotor/1.0\r\n"
                "\r\n"
            )
            
            # Send handshake
            self.socket.write(handshake_request.encode())
            
            # Read response with timeout
            response = b""
            start_time = time.ticks_ms()
            
            while b'\r\n\r\n' not in response:
                if time.ticks_diff(time.ticks_ms(), start_time) > 10000:  # 10 second timeout
                    print("Handshake timeout")
                    return False
                
                try:
                    chunk = self.socket.read(512)
                    if chunk:
                        response += chunk
                    else:
                        time.sleep_ms(10)
                except OSError:
                    time.sleep_ms(10)
            
            # Validate response
            response_str = response.decode('utf-8', 'ignore')
            if "101 Switching Protocols" in response_str:
                print("WebSocket handshake successful")
                return True
            else:
                print(f"Handshake failed: {response_str[:100]}")
                return False
                
        except Exception as e:
            print(f"Handshake error: {e}")
            return False
    
    def send_message(self, message_dict):
        """Send JSON message with optimized framing"""
        if not self.connected:
            return False
        
        try:
            # Convert to JSON and encode
            json_str = json.dumps(message_dict)
            payload = json_str.encode('utf-8')
            
            # Check message size
            if len(payload) > config.MAX_MESSAGE_SIZE:
                print(f"Message too large: {len(payload)} bytes")
                return False
            
            # Create WebSocket frame
            frame = self._create_text_frame(payload)
            
            # Send frame
            self.socket.write(frame)
            self.last_activity = time.ticks_ms()
            
            return True
            
        except Exception as e:
            print(f"Send message error: {e}")
            self.connected = False
            return False
    
    def _create_text_frame(self, payload):
        """Create WebSocket text frame with masking"""
        frame = bytearray()
        frame.append(0x81)  # FIN=1, opcode=1 (text)
        
        length = len(payload)
        mask_key = bytearray([urandom.getrandbits(8) for _ in range(4)])
        
        # Add length
        if length <= 125:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(length.to_bytes(2, 'big'))
        else:
            raise ValueError("Message too large")
        
        # Add mask key
        frame.extend(mask_key)
        
        # Mask and add payload
        for i in range(length):
            frame.append(payload[i] ^ mask_key[i % 4])
        
        return frame
    
    def receive_messages(self):
        """Receive and parse WebSocket messages"""
        if not self.connected:
            return []
        
        try:
            # Read available data
            data = self.socket.read(config.RECEIVE_CHUNK_SIZE)
            if not data:
                return []
            
            # Add to buffer
            self.receive_buffer.extend(data)
            self.last_activity = time.ticks_ms()
            
            # Prevent buffer overflow
            if len(self.receive_buffer) > config.MAX_BUFFER_SIZE:
                # Keep only recent data
                self.receive_buffer = self.receive_buffer[-config.RECEIVE_CHUNK_SIZE:]
            
            # Extract complete messages
            return self._extract_messages()
            
        except OSError:
            # Normal timeout, no data available
            return []
        except Exception as e:
            print(f"Receive error: {e}")
            self.connected = False
            return []
    
    def _extract_messages(self):
        """Extract complete JSON messages from buffer"""
        messages = []
        
        try:
            # Convert buffer to string
            text = self.receive_buffer.decode('utf-8', 'ignore')
            
            # Find complete JSON objects
            start = 0
            while start < len(text):
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
                    try:
                        # Validate JSON
                        json.loads(json_str)
                        messages.append(json_str)
                    except:
                        pass  # Skip invalid JSON
                    start = json_end
                else:
                    # Incomplete JSON, keep remaining
                    remaining = text[json_start:].encode('utf-8')
                    self.receive_buffer = bytearray(remaining)
                    break
            
            # Clear buffer if everything was processed
            if start >= len(text):
                self.receive_buffer = bytearray()
            
        except Exception as e:
            print(f"Message extraction error: {e}")
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
