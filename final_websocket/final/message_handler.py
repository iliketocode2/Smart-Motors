"""
Message handling and processing for SmartMotor communication
Handles CEEO channel protocol and device-specific message processing
"""

import json
import time
import config

class MessageHandler:
    def __init__(self, device_type, hardware_manager):
        """Initialize message handler with device type and hardware manager"""
        self.device_type = device_type
        self.hardware_manager = hardware_manager
        self.sequence_number = 0
        self.partner_sequence = 0
        self.last_angle_sent = 90
        self.current_servo_angle = 90
        
        # Set up topics based on device type
        if device_type == config.DEVICE_CONTROLLER:
            self.send_topic = "/controller/status"
            self.listen_topic = "/receiver/status"
        else:
            self.send_topic = "/receiver/status"  
            self.listen_topic = "/controller/status"
    
    def create_data_message(self, data_type, value):
        """Create a data message with proper structure"""
        self.sequence_number += 1
        
        message = {
            "device": self.device_type,
            "sequence": self.sequence_number,
            "timestamp": time.ticks_ms(),
            "type": data_type
        }
        
        # Add device-specific data
        if self.device_type == config.DEVICE_CONTROLLER:
            message["potentiometer_angle"] = value
        else:
            message["servo_angle"] = value
        
        return {
            "topic": self.send_topic,
            "value": message
        }
    
    def create_heartbeat_message(self):
        """Create a heartbeat message"""
        self.sequence_number += 1
        
        return {
            "topic": self.send_topic,
            "value": {
                "device": self.device_type,
                "sequence": self.sequence_number,
                "timestamp": time.ticks_ms(),
                "type": "heartbeat",
                "partner_sequence": self.partner_sequence
            }
        }
    
    def process_received_message(self, message_str):
        """Process incoming message and return action to take"""
        try:
            # Parse CEEO channel message
            channel_message = json.loads(message_str)
            
            # Handle welcome message
            if channel_message.get('type') == 'welcome':
                print("Channel connection established")
                return None
            
            # Handle data messages
            if channel_message.get('type') == 'data' and 'payload' in channel_message:
                payload_str = channel_message['payload']
                payload = json.loads(payload_str)
                
                topic = payload.get('topic', '')
                value = payload.get('value', {})
                
                # Check if message is for this device
                if topic == self.listen_topic:
                    return self._process_device_message(value)
            
            return None
            
        except Exception as e:
            print(f"Message processing error: {e}")
            return None
    
    def _process_device_message(self, data):
        """Process device-specific message data"""
        if not isinstance(data, dict):
            return None
        
        # Update partner sequence
        if 'sequence' in data:
            self.partner_sequence = data['sequence']
        
        message_type = data.get('type', 'data')
        
        if message_type == 'heartbeat':
            print(f"Received heartbeat from partner (seq #{self.partner_sequence})")
            return None
        
        # Handle data messages based on device type
        if self.device_type == config.DEVICE_RECEIVER:
            return self._handle_receiver_message(data)
        else:
            return self._handle_controller_message(data)
    
    def _handle_receiver_message(self, data):
        """Handle messages for receiver device (servo control)"""
        if 'potentiometer_angle' in data:
            angle = data['potentiometer_angle']
            if isinstance(angle, (int, float)):
                angle = max(0, min(180, int(angle)))
                
                # Move servo and update display
                if self.hardware_manager.move_servo(angle):
                    self.current_servo_angle = angle
                    self.hardware_manager.update_display(
                        "RECEIVER",
                        f"Servo: {angle}°",
                        f"Partner: #{self.partner_sequence}",
                        f"Me: #{self.sequence_number}"
                    )
                    
                    # Return action to send servo status
                    return {
                        'action': 'send_servo_status',
                        'angle': angle
                    }
        
        return None
    
    def _handle_controller_message(self, data):
        """Handle messages for controller device (display servo status)"""
        if 'servo_angle' in data:
            angle = data['servo_angle']
            self.hardware_manager.update_display(
                "CONTROLLER",
                f"Remote: {angle}°",
                f"Partner: #{self.partner_sequence}",
                f"Me: #{self.sequence_number}"
            )
        
        return None
    
    def should_send_potentiometer_data(self):
        """Check if controller should send potentiometer data"""
        if self.device_type != config.DEVICE_CONTROLLER:
            return False, 0
        
        current_angle = self.hardware_manager.read_potentiometer()
        
        # Check if angle changed significantly
        if abs(current_angle - self.last_angle_sent) >= config.ANGLE_CHANGE_THRESHOLD:
            self.last_angle_sent = current_angle
            return True, current_angle
        
        return False, current_angle
    
    def update_controller_display(self, angle):
        """Update display for controller device"""
        if self.device_type == config.DEVICE_CONTROLLER:
            self.hardware_manager.update_display(
                "CONTROLLER",
                f"Knob: {angle}°",
                f"Partner: #{self.partner_sequence}",
                f"Me: #{self.sequence_number}"
            )
    
    def get_sequence_number(self):
        """Get current sequence number"""
        return self.sequence_number
    
    def get_partner_sequence(self):
        """Get partner sequence number"""
        return self.partner_sequence
