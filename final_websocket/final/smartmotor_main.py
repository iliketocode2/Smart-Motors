"""
Main controller for ESP32 SmartMotor system
Coordinates all components with improved stability and error handling
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
        """Initialize SmartMotor controller with specified device type"""
        self.device_type = device_type
        self.running = True
        self.connection_stable = False
        
        # Initialize managers
        self.hardware = HardwareManager(device_type)
        self.wifi = WiFiManager(self.hardware)
        self.websocket = WebSocketManager(self.hardware)
        self.message_handler = MessageHandler(device_type, self.hardware)
        
        # Timing and state management
        self.last_send_time = 0
        self.last_heartbeat_time = 0
        self.reconnect_attempts = 0
        
        print("SmartMotor {} initialized".format(device_type))
        print("Send topic: {}".format(self.message_handler.send_topic))
        print("Listen topic: {}".format(self.message_handler.listen_topic))
    
    def run(self):
        """Main execution loop with improved error recovery"""
        try:
            # Initialize connection
            if not self._initialize_connections():
                print("Failed to initialize connections")
                return
            
            # Start communication loop
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
        
        # Connect to WiFi
        if not self.wifi.connect():
            return False
        
        # Connect to WebSocket with retries
        for attempt in range(config.MAX_RECONNECT_ATTEMPTS):
            if self.websocket.connect():
                self.connection_stable = True
                return True
            
            print("WebSocket connection attempt {} failed".format(attempt + 1))
            if attempt < config.MAX_RECONNECT_ATTEMPTS - 1:
                time.sleep(config.RECONNECTION_DELAY_S)
        
        return False
    
    def _start_communication_threads(self):
        """Start communication threads or single-threaded fallback"""
        try:
            # Try to start threaded communication
            _thread.start_new_thread(self._message_sender_thread, ())
            print("Message sender thread started")
            
            # Main thread handles message receiving
            self._message_receiver_loop()
            
        except:
            print("Threading not available, using single-threaded mode")
            self._single_threaded_loop()
    
    def _message_sender_thread(self):
        """Background thread for sending messages"""
        print("Message sender thread running")
        
        while self.running:
            try:
                if not self.connection_stable:
                    time.sleep(1)
                    continue
                
                current_time = time.ticks_ms()
                
                # Handle device-specific sending
                if self.device_type == config.DEVICE_CONTROLLER:
                    self._handle_controller_sending(current_time)
                
                # Send heartbeat if needed
                self._send_heartbeat_if_needed(current_time)
                
                # Check connection health
                if not self.websocket.is_connected():
                    print("Connection lost in sender thread")
                    self.connection_stable = False
                    self._attempt_reconnection()
                
                time.sleep_ms(50)  # Small delay to prevent overwhelming
                
            except Exception as e:
                print("Sender thread error: {}".format(e))
                time.sleep(1)
    
    def _message_receiver_loop(self):
        """Main loop for receiving and processing messages"""
        print("Message receiver loop running")
        
        while self.running:
            try:
                if not self.connection_stable:
                    time.sleep(1)
                    continue
                
                # Receive and process messages
                messages = self.websocket.receive_messages()
                for message_data in messages:
                    # Handle both fragment dict and complete JSON string
                    if isinstance(message_data, dict):
                        # Fragment message
                        self._process_received_message(message_data)
                    else:
                        # Complete JSON message
                        print("Raw message received: {}".format(message_data[:100]))
                        self._process_received_message(message_data)
                
                # Check connection health
                if not self.websocket.is_connected():
                    print("Connection lost in receiver loop")
                    self.connection_stable = False
                    self._attempt_reconnection()
                
                time.sleep_ms(20)  # Small delay
                
            except Exception as e:
                print("Receiver loop error: {}".format(e))
                time.sleep(1)
    
    def _single_threaded_loop(self):
        """Fallback single-threaded communication loop"""
        print("Running in single-threaded mode")
        
        while self.running:
            try:
                if not self.connection_stable:
                    if not self._attempt_reconnection():
                        time.sleep(5)
                        continue
                
                current_time = time.ticks_ms()
                
                # Receive messages
                messages = self.websocket.receive_messages()
                for message_data in messages:
                    # Handle both fragment dict and complete JSON string
                    if isinstance(message_data, dict):
                        # Fragment message
                        self._process_received_message(message_data)
                    else:
                        # Complete JSON message
                        print("Raw message received: {}".format(message_data[:100]))
                        self._process_received_message(message_data)
                
                # Send data based on device type
                if self.device_type == config.DEVICE_CONTROLLER:
                    self._handle_controller_sending(current_time)
                
                # Send heartbeat
                self._send_heartbeat_if_needed(current_time)
                
                # Check connection
                if not self.websocket.is_connected():
                    self.connection_stable = False
                
                time.sleep_ms(100)
                
            except Exception as e:
                print("Single-threaded loop error: {}".format(e))
                time.sleep(1)
    
    def _handle_controller_sending(self, current_time):
        """Handle sending for controller device - simplified"""
        if time.ticks_diff(current_time, self.last_send_time) < config.SEND_INTERVAL_MS:
            return
        
        should_send, angle = self.message_handler.should_send_potentiometer_data()
        
        if should_send:
            message = self.message_handler.create_data_message(angle)
            
            if self.websocket.send_message(message):
                self.last_send_time = current_time
                print("Sent angle: {}°".format(angle))
            else:
                print("Failed to send angle")
                self.connection_stable = False
    
    def _send_heartbeat_if_needed(self, current_time):
        """Send heartbeat message if interval has elapsed - simplified"""
        if time.ticks_diff(current_time, self.last_heartbeat_time) > config.HEARTBEAT_INTERVAL_MS:
            message = self.message_handler.create_heartbeat_message()
            
            if self.websocket.send_message(message):
                self.last_heartbeat_time = current_time
                print("Heartbeat sent")
            else:
                print("Heartbeat failed")
                self.connection_stable = False
    
    def _process_received_message(self, message_data):
        """Process a received message - simplified"""
        try:
            action = self.message_handler.process_received_message(message_data)
            
            if action and action.get('action') == 'send_confirmation':
                # Receiver sending confirmation back
                angle = action['angle']
                message = self.message_handler.create_data_message(angle)
                
                if self.websocket.send_message(message):
                    print("Confirmed: {}°".format(angle))
        except Exception as e:
            print("Process error: {}".format(e))
    
    def _attempt_reconnection(self):
        """Attempt to reconnect to WebSocket"""
        if self.reconnect_attempts >= config.MAX_RECONNECT_ATTEMPTS:
            print("Max reconnection attempts reached")
            return False
        
        print("Attempting reconnection #{}".format(self.reconnect_attempts + 1))
        self.hardware.update_display("SmartMotor", "Reconnecting", "Attempt {}".format(self.reconnect_attempts + 1), "")
        
        self.reconnect_attempts += 1
        
        # Check WiFi first
        if not self.wifi.is_connected():
            print("WiFi disconnected, reconnecting...")
            if not self.wifi.connect():
                return False
        
        # Reconnect WebSocket
        if self.websocket.connect():
            self.connection_stable = True
            self.reconnect_attempts = 0
            print("Reconnection successful")
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
        
        # Force garbage collection
        gc.collect()
        print("Cleanup complete")

# Main entry point
if __name__ == "__main__":
    # Configuration - change this for different devices
    DEVICE_MODE = config.DEVICE_CONTROLLER  # Change to config.DEVICE_RECEIVER for servo device
    
    try:
        controller = SmartMotorController(DEVICE_MODE)
        controller.run()
    except Exception as e:
        print("Fatal error: {}".format(e))
    finally:
        print("SmartMotor controller stopped")
