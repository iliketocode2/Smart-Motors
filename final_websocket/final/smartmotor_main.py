"""
Main controller for ESP32 SmartMotor system - UPDATED to use config values
All timing and rate limiting values now come from config.py
"""

import time
import gc
import _thread
import config
from hardware_manager import HardwareManager
from wifi_manager import WiFiManager
from websocket_manager import WebSocketManager
from message_handler import MessageHandler

class SmartMotorController:
    def __init__(self, device_type):
        """Initialize SmartMotor controller using config values"""
        self.device_type = device_type
        self.running = True
        self.connection_stable = False
        
        # Initialize managers
        self.hardware = HardwareManager(device_type)
        self.wifi = WiFiManager(self.hardware)
        self.websocket = WebSocketManager(self.hardware)
        self.message_handler = MessageHandler(device_type, self.hardware)
        
        # State synchronization tracking
        self.last_send_time = 0
        self.last_heartbeat_time = 0
        self.reconnect_attempts = 0
        self.last_known_angle = 90
        self.connection_established_time = 0
        self.need_state_sync = False
        
        # Rate limiting using config values
        self.message_count = 0
        self.message_window_start = 0
        
        print("SmartMotor {} initialized (USES CONFIG)".format(device_type))
        print("Send topic: {}".format(self.message_handler.send_topic))
        print("Listen topic: {}".format(self.message_handler.listen_topic))
    
    def run(self):
        """Main execution loop"""
        try:
            if not self._initialize_connections():
                print("Failed to initialize connections")
                return
            
            self._start_communication_threads()
            
        except KeyboardInterrupt:
            print("Shutdown requested by user")
        except Exception as e:
            print(f"Critical error in main loop: {e}")
        finally:
            self._cleanup()
    
    def _initialize_connections(self):
        """Initialize WiFi and WebSocket connections"""
        print("Initializing connections...")
        
        if not self.wifi.connect():
            return False
        
        # Use config value for max attempts
        for attempt in range(config.MAX_RECONNECT_ATTEMPTS):
            if self.websocket.connect():
                self.connection_stable = True
                self.connection_established_time = time.ticks_ms()
                self.need_state_sync = True
                return True
            
            print("WebSocket connection attempt {} failed".format(attempt + 1))
            if attempt < config.MAX_RECONNECT_ATTEMPTS - 1:
                time.sleep(config.RECONNECTION_DELAY_S)  # Use config value
        
        return False
    
    def _start_communication_threads(self):
        """Start communication threads"""
        try:
            _thread.start_new_thread(self._sender_thread, ())
            print("Sender thread started")
            
            self._receiver_loop()
            
        except:
            print("Threading not available, using single-threaded mode")
            self._single_threaded_loop()
    
    def _sender_thread(self):
        """Sender thread using config values"""
        print("Sender thread running")
        
        while self.running:
            try:
                if not self.connection_stable:
                    time.sleep(1)
                    continue
                
                current_time = time.ticks_ms()
                
                # Check rate limiting using config values
                if not self._can_send_message(current_time):
                    time.sleep_ms(100)
                    continue
                
                # Send state sync if needed
                if self.need_state_sync and self._time_since_connection(current_time) > config.STATE_SYNC_DELAY_MS:
                    self._send_state_sync(current_time)
                    self.need_state_sync = False
                
                # Handle device-specific sending
                data_sent = False
                if self.device_type == config.DEVICE_CONTROLLER:
                    data_sent = self._handle_controller_sending(current_time)
                
                # Send heartbeat if no data sent
                if not data_sent and self._should_send_heartbeat(current_time):
                    self._send_heartbeat(current_time)
                
                # Check connection health
                if not self.websocket.is_connected():
                    print("Connection lost in sender thread")
                    self.connection_stable = False
                    self._attempt_reconnection()
                
                time.sleep_ms(50)  # Small delay between iterations
                
            except Exception as e:
                print("Sender thread error: {}".format(e))
                time.sleep(1)
    
    def _receiver_loop(self):
        """Receiver loop"""
        print("Receiver loop running")
        
        while self.running:
            try:
                if not self.connection_stable:
                    time.sleep(1)
                    continue
                
                messages = self.websocket.receive_messages()
                for message_data in messages:
                    self._process_received_message(message_data)
                
                if not self.websocket.is_connected():
                    print("Connection lost in receiver loop")
                    self.connection_stable = False
                    self._attempt_reconnection()
                
                time.sleep_ms(20)
                
            except Exception as e:
                print("Receiver loop error: {}".format(e))
                time.sleep(1)
    
    def _single_threaded_loop(self):
        """Single-threaded fallback"""
        print("Running in single-threaded mode")
        
        while self.running:
            try:
                if not self.connection_stable:
                    if not self._attempt_reconnection():
                        time.sleep(5)
                        continue
                
                current_time = time.ticks_ms()
                
                # Process messages first
                messages = self.websocket.receive_messages()
                for message_data in messages:
                    self._process_received_message(message_data)
                
                # Handle sending with rate limiting
                if self._can_send_message(current_time):
                    # State sync if needed
                    if self.need_state_sync and self._time_since_connection(current_time) > config.STATE_SYNC_DELAY_MS:
                        self._send_state_sync(current_time)
                        self.need_state_sync = False
                    else:
                        # Normal data sending
                        data_sent = False
                        if self.device_type == config.DEVICE_CONTROLLER:
                            data_sent = self._handle_controller_sending(current_time)
                        
                        # Heartbeat if no data sent
                        if not data_sent and self._should_send_heartbeat(current_time):
                            self._send_heartbeat(current_time)
                
                # Check connection
                if not self.websocket.is_connected():
                    self.connection_stable = False
                
                time.sleep_ms(30)
                
            except Exception as e:
                print("Single-threaded loop error: {}".format(e))
                time.sleep(1)
    
    def _can_send_message(self, current_time):
        """Check if we can send a message without hitting rate limits (uses config values)"""
        # Reset window if needed
        if time.ticks_diff(current_time, self.message_window_start) > config.MESSAGE_WINDOW_MS:
            self.message_window_start = current_time
            self.message_count = 0
        
        return self.message_count < config.MAX_MESSAGES_PER_WINDOW
    
    def _time_since_connection(self, current_time):
        """Get time since connection was established"""
        return time.ticks_diff(current_time, self.connection_established_time)
    
    def _send_state_sync(self, current_time):
        """Send current state immediately after reconnection"""
        if self.device_type == config.DEVICE_CONTROLLER:
            current_angle = self.hardware.read_potentiometer()
            message = self.message_handler.create_data_message(current_angle)
            
            if self.websocket.send_message(message):
                self.last_send_time = current_time
                self.message_count += 1
                print("State sync sent: {}°".format(current_angle))
                self.last_known_angle = current_angle
        elif self.device_type == config.DEVICE_RECEIVER:
            message = self.message_handler.create_data_message(self.last_known_angle)
            
            if self.websocket.send_message(message):
                self.message_count += 1
                print("State sync confirmed: {}°".format(self.last_known_angle))
    
    def _handle_controller_sending(self, current_time):
        """Handle controller sending using config timing"""
        # Use config value for send interval
        if time.ticks_diff(current_time, self.last_send_time) < config.SEND_INTERVAL_MS:
            return False
        
        should_send, angle = self.message_handler.should_send_potentiometer_data()
        
        if should_send:
            message = self.message_handler.create_data_message(angle)
            
            if self.websocket.send_message(message):
                self.last_send_time = current_time
                self.message_count += 1
                print("Sent angle: {}°".format(angle))
                self.last_known_angle = angle
                return True
            else:
                print("Failed to send angle")
                self.connection_stable = False
        
        return False
    
    def _should_send_heartbeat(self, current_time):
        """Check if heartbeat should be sent using config timing"""
        return time.ticks_diff(current_time, self.last_heartbeat_time) > config.HEARTBEAT_INTERVAL_MS
    
    def _send_heartbeat(self, current_time):
        """Send heartbeat"""
        message = self.message_handler.create_heartbeat_message()
        
        if self.websocket.send_message(message):
            self.last_heartbeat_time = current_time
            self.message_count += 1
            print("Heartbeat sent")
        else:
            print("Heartbeat failed")
            self.connection_stable = False
    
    def _process_received_message(self, message_data):
        """Process received messages"""
        try:
            action = self.message_handler.process_received_message(message_data)
            
            if action and action.get('action') == 'send_confirmation':
                current_time = time.ticks_ms()
                if self._can_send_message(current_time):
                    angle = action['angle']
                    message = self.message_handler.create_data_message(angle)
                    
                    if self.websocket.send_message(message):
                        self.message_count += 1
                        print("Confirmed: {}°".format(angle))
                        self.last_known_angle = angle
                    
        except Exception as e:
            print("Process error: {}".format(e))
    
    def _attempt_reconnection(self):
        """Attempt to reconnect"""
        if self.reconnect_attempts >= config.MAX_RECONNECT_ATTEMPTS:
            print("Max reconnection attempts reached")
            return False
        
        print("Attempting reconnection #{}".format(self.reconnect_attempts + 1))
        self.hardware.update_display("SmartMotor", "Reconnecting", "Attempt {}".format(self.reconnect_attempts + 1), "")
        
        self.reconnect_attempts += 1
        
        if not self.wifi.is_connected():
            print("WiFi disconnected, reconnecting...")
            if not self.wifi.connect():
                return False
        
        if self.websocket.connect():
            self.connection_stable = True
            self.reconnect_attempts = 0
            self.connection_established_time = time.ticks_ms()
            self.need_state_sync = True
            print("Reconnection successful - state sync needed")
            return True
        
        return False
    
    def _cleanup(self):
        """Clean up resources"""
        print("Cleaning up...")
        self.running = False
        self.connection_stable = False
        
        if self.websocket:
            self.websocket.close()
        
        if self.wifi:
            self.wifi.disconnect()
        
        if self.hardware:
            self.hardware.cleanup()
        
        gc.collect()
        print("Cleanup complete")

# Main entry point
if __name__ == "__main__":
    DEVICE_MODE = config.DEVICE_CONTROLLER  # Change to config.DEVICE_RECEIVER for servo device
    
    try:
        controller = SmartMotorController(DEVICE_MODE)
        controller.run()
    except Exception as e:
        print("Fatal error: {}".format(e))
    finally:
        print("SmartMotor controller stopped")
