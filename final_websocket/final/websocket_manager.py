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
        """Initialize WebSocket manager with complete message buffering"""
        self.hardware_manager = hardware_manager
        self.socket = None
        self.connected = False
        self.receive_buffer = bytearray()
        self.connection_attempts = 0
        self.last_activity = time.ticks_ms()
        
        # Complete message assembly
        self.raw_accumulator = bytearray()  # Raw bytes until complete
        self.max_message_size = 2048  # Maximum single message size
        self.read_timeout_count = 0
        
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
        """Conservative approach - prioritize stability over speed"""
        if not self.connected:
            return []
        
        try:
            # Read data
            data = self.socket.read(config.RECEIVE_CHUNK_SIZE)
            if data:
                self.raw_accumulator.extend(data)
                
                # Use conservative threshold - wait for more complete data
                if len(self.raw_accumulator) > 400:  # Back to stable threshold
                    
                    messages = self.extract_complete_json_messages()
                    if messages:
                        # Conservative buffer management - only clear processed parts
                        text = self.safe_decode(self.raw_accumulator)
                        if text:
                            # Find last complete message end
                            last_end = text.rfind('}}')
                            if last_end != -1:
                                # Keep remainder after last complete message
                                remainder = text[last_end + 2:].strip()
                                if remainder:
                                    self.raw_accumulator = bytearray(remainder.encode('utf-8'))
                                else:
                                    self.raw_accumulator = bytearray()
                            else:
                                self.raw_accumulator = bytearray()
                        return messages
                    
                    # Clear buffer if it gets too large without finding messages
                    elif len(self.raw_accumulator) > self.max_message_size:
                        self.raw_accumulator = bytearray()
                
        except OSError:
            # Normal timeout
            pass
        except Exception as e:
            print("Receive error: {}".format(e))
            self.connected = False
        
        return []
    
    def extract_fragment_data(self):
        """Extract essential data from fragments - handle both old and new topic formats"""
        try:
            # Convert buffer to text
            text = self.safe_decode(self.raw_accumulator)
            if not text:
                return []
            
            # Look for controller data - handle both formats
            if ('/controller/data' in text or '/controller/status' in text) and 'value' in text:
                angle = self._extract_angle_from_text(text)
                if angle is not None:
                    print("Fragment: {}°".format(angle))
                    return [{
                        'type': 'fragment',
                        'topic': '/controller/data',  # Normalize to new format
                        'potentiometer_angle': angle
                    }]
            
            # Look for receiver data - handle both formats
            if ('/receiver/data' in text or '/receiver/status' in text) and 'value' in text:
                angle = self._extract_angle_from_text(text)
                if angle is not None:
                    print("Fragment servo: {}°".format(angle))
                    return [{
                        'type': 'fragment',
                        'topic': '/receiver/data',  # Normalize to new format
                        'servo_angle': angle
                    }]
            
        except Exception as e:
            pass
        
        return []
    
    def _extract_angle_from_text(self, text):
        """Quickly extract angle value from text"""
        try:
            # Look for "value": followed by a number
            value_pos = text.find('"value":')
            if value_pos != -1:
                # Find the number after "value":
                start = value_pos + 8  # Length of "value":
                end = start
                
                # Skip whitespace and potential quotes
                while end < len(text) and text[end] in ' "':
                    end += 1
                
                # Extract digits
                num_start = end
                while end < len(text) and (text[end].isdigit() or text[end] == '.'):
                    end += 1
                
                if end > num_start:
                    angle_str = text[num_start:end]
                    return int(float(angle_str))
            
        except Exception as e:
            pass
        
        return None
    
    def safe_decode(self, data):
        """Safely decode bytes to string - MicroPython compatible with fixed error handling"""
        try:
            if isinstance(data, bytes):
                return data.decode('utf-8')
            elif isinstance(data, bytearray):
                return bytes(data).decode('utf-8')
            else:
                return str(data)
        except (Exception, NameError) as e:
            print("Decode error: {}".format(e))
            # Extract printable characters directly
            result = ""
            for byte in data:
                if 32 <= byte <= 126:  # Printable ASCII
                    result += chr(byte)
            return result
    
    def has_complete_messages(self):
        """Check if buffer contains what looks like complete CEEO messages"""
        try:
            text = self.safe_decode(self.raw_accumulator)
            
            # Look for complete CEEO message patterns
            # A complete message should have: {"client_id":"...","type":"...","payload":"..."}
            
            # Count opening and closing braces to see if we have complete JSON
            open_braces = text.count('{')
            close_braces = text.count('}')
            
            # For CEEO messages, we typically need at least 2 levels of nesting
            # Outer: {"client_id":...}
            # Inner: {"topic":...} in payload
            
            if open_braces >= 2 and close_braces >= 2 and open_braces == close_braces:
                # Look for specific CEEO patterns
                if ('{"client_id"' in text and '"type":"data"' in text and 
                    '"payload"' in text and text.count('}}') >= 1):
                    return True
                elif '{"client_id"' in text and '"type":"welcome"' in text:
                    return True
            
            return False
            
        except:
            return False
    
    def extract_complete_json_messages(self):
        """Back to reliable extraction - no fragment processing"""
        messages = []
        
        try:
            # Decode buffer
            text = self.safe_decode(self.raw_accumulator)
            if not text or len(text) < 100:
                return messages
            
            # Remove leading 'T' if present
            if text.startswith('T{"client_id"'):
                text = text[1:]
            
            # Look for complete JSON messages using reliable brace counting
            pos = 0
            while pos < len(text):
                # Find start of JSON message
                json_start = text.find('{"client_id"', pos)
                if json_start == -1:
                    break
                
                # Find the end by balancing braces carefully
                brace_count = 0
                json_end = -1
                
                for i in range(json_start, len(text)):
                    char = text[i]
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break
                
                if json_end != -1:
                    # Extract complete message
                    message_text = text[json_start:json_end]
                    
                    # Only process substantial messages
                    if len(message_text) > 100:
                        try:
                            # Validate JSON
                            parsed = json.loads(message_text)
                            messages.append(message_text)
                        except:
                            # Skip invalid JSON silently
                            pass
                    
                    pos = json_end
                else:
                    # No complete message found
                    break
            
        except:
            # Silent error handling
            pass
        
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
        self.raw_accumulator = bytearray()
        gc.collect()
    
    def close(self):
        """Close WebSocket connection"""
        print("Closing WebSocket connection")
        self._cleanup_socket()
