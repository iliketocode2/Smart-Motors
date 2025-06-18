"""
WebSocket connection manager OPTIMIZED for CEEO channel persistence
Key fixes for channel subscription persistence:
- Immediate state sync after reconnection
- Lightweight keepalive messages
- Better connection health monitoring  
- Proper channel re-subscription handling
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
        """Initialize WebSocket manager optimized for channel persistence"""
        self.hardware_manager = hardware_manager
        self.socket = None
        self.connected = False
        self.connection_attempts = 0
        self.last_activity = time.ticks_ms()
        
        # CRITICAL: Track channel subscription state
        self.channel_subscribed = False
        self.last_data_sent = 0
        self.last_data_received = 0
        
        # Optimized buffer management for channel persistence
        self.raw_accumulator = bytearray(800)  # Medium size to handle channel messages
        self.accumulator_len = 0
        self.max_message_size = 800
        
        # Pre-allocate buffers
        self.read_buffer = bytearray(256)
        
    def generate_websocket_key(self):
        """Generate WebSocket key"""
        key_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
        return ubinascii.b2a_base64(key_bytes).decode().strip()
    
    def connect(self):
        """Establish WebSocket connection with channel subscription tracking"""
        try:
            if self.hardware_manager:
                self.hardware_manager.update_display("SmartMotor", "WebSocket", "Connecting...", "")
            
            print("Connecting to WebSocket...")
            
            # Clean up any existing connection
            self._cleanup_socket()
            
            # Reset connection AND channel state
            self.connection_attempts = 0
            self.last_activity = time.ticks_ms()
            self.accumulator_len = 0
            self.channel_subscribed = False  # CRITICAL: Reset channel subscription
            
            # Resolve address
            addr_info = socket.getaddrinfo(config.WS_HOST, config.WS_PORT)
            addr = addr_info[0][-1]
            
            # Create SSL socket
            raw_sock = socket.socket()
            raw_sock.settimeout(10)
            raw_sock.connect(addr)
            self.socket = ussl.wrap_socket(raw_sock, server_hostname=config.WS_HOST)
            
            # WebSocket handshake
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
            
            # Read handshake response
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
                
                # Initialize timing
                current_time = time.ticks_ms()
                self.last_activity = current_time
                self.last_data_sent = current_time  # Initialize data timing
                self.last_data_received = current_time
                
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
        """Send JSON message with activity tracking"""
        if not self.connected:
            return False
        
        try:
            json_data = json.dumps(message_dict)
            payload = json_data.encode('utf-8')
            length = len(payload)
            
            # CRITICAL: Check for network rate limiting
            if length > config.MAX_MESSAGE_SIZE:
                print("Message too large, skipping")
                return False
            
            # Create WebSocket frame
            frame = bytearray()
            frame.append(0x81)  # FIN=1, opcode=1 (text)
            
            # Generate mask key
            mask_key = bytearray([urandom.getrandbits(8) for _ in range(4)])
            
            # Add length and mask bit
            if length <= 125:
                frame.append(0x80 | length)
            elif length < 65536:
                frame.append(0x80 | 126)
                frame.extend(length.to_bytes(2, 'big'))
            else:
                return False
            
            # Add mask key
            frame.extend(mask_key)
            
            # Mask and add payload
            for i in range(length):
                frame.append(payload[i] ^ mask_key[i % 4])
            
            # Send with activity tracking
            self.socket.write(frame)
            current_time = time.ticks_ms()
            self.last_activity = current_time
            self.last_data_sent = current_time  # Track data sending
            
            return True
            
        except Exception as e:
            print("Send message error: {}".format(e))
            self.connected = False
            return False
    
    def receive_messages(self):
        """Optimized message processing with channel persistence tracking"""
        if not self.connected:
            return []
        
        try:
            bytes_read = self.socket.readinto(self.read_buffer)
            if bytes_read:
                # Manage buffer efficiently
                if self.accumulator_len + bytes_read > len(self.raw_accumulator):
                    # Buffer management: keep recent data, discard old
                    keep_size = len(self.raw_accumulator) // 2
                    self.raw_accumulator[:keep_size] = self.raw_accumulator[self.accumulator_len - keep_size:self.accumulator_len]
                    self.accumulator_len = keep_size
                
                # Copy new data
                self.raw_accumulator[self.accumulator_len:self.accumulator_len + bytes_read] = self.read_buffer[:bytes_read]
                self.accumulator_len += bytes_read
                
                # Process messages with lower threshold for responsiveness
                if self.accumulator_len > 120:  # Lower threshold
                    messages = self.extract_complete_json_messages_fast()
                    if messages:
                        # Track data reception
                        self.last_data_received = time.ticks_ms()
                        self._compact_buffer_after_processing()
                        return messages
                    
                    # Aggressive buffer management
                    elif self.accumulator_len > self.max_message_size:
                        self.accumulator_len = 0
                
        except OSError:
            # Normal timeout
            pass
        except Exception as e:
            print("Receive error: {}".format(e))
            self.connected = False
        
        return []
    
    def extract_complete_json_messages_fast(self):
        """Fast message extraction optimized for CEEO channel messages"""
        messages = []
        
        try:
            if self.accumulator_len < 80:  # Minimum CEEO message size
                return messages
            
            # Convert used portion of buffer
            text = self.safe_decode_fast(self.raw_accumulator[:self.accumulator_len])
            if not text:
                return messages
            
            # Handle CEEO channel message format
            pos = 0
            while pos < len(text):
                # Look for CEEO channel messages
                json_start = text.find('{"client_id"', pos)
                if json_start == -1:
                    break
                
                # Find end by brace counting
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
                    message_text = text[json_start:json_end]
                    
                    # Process CEEO channel messages
                    if len(message_text) > 80:  # Valid CEEO message size
                        try:
                            # Quick validation for CEEO format
                            if ('"type":"data"' in message_text and '"payload"' in message_text) or '"type":"welcome"' in message_text:
                                messages.append(message_text)
                                
                                # CRITICAL: Track channel subscription on welcome
                                if '"type":"welcome"' in message_text:
                                    self.channel_subscribed = True
                                    print("Channel subscription confirmed")
                        except:
                            pass
                    
                    pos = json_end
                else:
                    break
            
        except:
            pass
        
        return messages
    
    def _compact_buffer_after_processing(self):
        """Efficient buffer compaction"""
        try:
            text = self.safe_decode_fast(self.raw_accumulator[:self.accumulator_len])
            if text:
                last_end = text.rfind('}}')
                if last_end != -1:
                    byte_pos = min(last_end + 2, self.accumulator_len)
                    remainder_len = self.accumulator_len - byte_pos
                    if remainder_len > 0:
                        self.raw_accumulator[:remainder_len] = self.raw_accumulator[byte_pos:self.accumulator_len]
                        self.accumulator_len = remainder_len
                    else:
                        self.accumulator_len = 0
                else:
                    self.accumulator_len = 0
            else:
                self.accumulator_len = 0
        except:
            self.accumulator_len = 0
    
    def safe_decode_fast(self, data):
        """Fast decode with minimal overhead"""
        try:
            return bytes(data).decode('utf-8')
        except:
            # Minimal fallback
            result = ""
            for byte in data:
                if 32 <= byte <= 126:
                    result += chr(byte)
            return result
    
    def is_connected(self):
        """Enhanced connection checking with channel subscription awareness"""
        if not self.connected:
            return False
        
        current_time = time.ticks_ms()
        
        # CRITICAL: Check for silent disconnection via data activity
        time_since_last_received = time.ticks_diff(current_time, self.last_data_received)
        
        # If we haven't received data in a while, connection might be stale
        if time_since_last_received > config.MESSAGE_TIMEOUT_MS:
            print("No data received recently, connection may be stale")
            self.connected = False
            return False
        
        # Standard timeout check
        if time.ticks_diff(current_time, self.last_activity) > config.MESSAGE_TIMEOUT_MS:
            print("Connection timeout detected")
            self.connected = False
            return False
        
        return True
    
    def needs_state_sync(self):
        """Check if we need to send state sync after reconnection"""
        return self.connected and self.channel_subscribed and (
            time.ticks_diff(time.ticks_ms(), self.last_data_sent) > 2000  # 2 seconds since last send
        )
    
    def _cleanup_socket(self):
        """Clean up socket resources"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        self.connected = False
        self.channel_subscribed = False  # Reset channel state
        self.accumulator_len = 0
        gc.collect()
    
    def close(self):
        """Close WebSocket connection"""
        print("Closing WebSocket connection")
        self._cleanup_socket()
