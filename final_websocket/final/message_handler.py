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
        
        # Add missing attributes from original
        self.last_message_received = 0
        self.partner_alive = False
        
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
        """Process incoming message - using original draft2.py logic"""
        try:
            self.last_message_received = time.ticks_ms()
            self.partner_alive = True
            
            # Parse CEEO channel message
            channel_msg = json.loads(message_str)
            
            if channel_msg.get('type') == 'welcome':
                print("Channel connection confirmed")
                return None
            
            if channel_msg.get('type') == 'data' and 'payload' in channel_msg:
                payload_str = channel_msg['payload']
                payload = json.loads(payload_str)
                topic = payload.get('topic', '')
                value = payload.get('value', {})
                
                # Track partner sequence if available
                if isinstance(value, dict) and 'sequence' in value:
                    self.partner_sequence = value['sequence']
                
                print("Received #{}: {} -> {}".format(self.partner_sequence, topic, self.listen_topic))
                
                # Check if this message is for us
                if topic == self.listen_topic:
                    print("Processing message for this device")
                    return self._process_device_message(value)
                else:
                    print("Message not for this device")
                    
        except Exception as e:
            print("Message handling error: {}".format(e))
        
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
            print("Received heartbeat from partner (seq #{})".format(self.partner_sequence))
            return None
        
        # Handle data messages based on device type
        if self.device_type == config.DEVICE_RECEIVER:
            return self._handle_receiver_message(data)
        else:
            return self._handle_controller_message(data)
    
    def _handle_receiver_message(self, data):
        """Handle messages for receiver device (servo control)"""
        print("Receiver processing data: {}".format(data))
        
        if 'potentiometer_angle' in data:
            angle = data['potentiometer_angle']
            print("Found potentiometer_angle: {}".format(angle))
            
            if isinstance(angle, (int, float)):
                angle = max(0, min(180, int(angle)))
                print("Moving servo to angle: {}".format(angle))
                
                # Move servo and update display
                if self.hardware_manager.move_servo(angle):
                    self.current_servo_angle = angle
                    print("Servo moved successfully to: {}°".format(angle))
                    
                    self.hardware_manager.update_display(
                        "RECEIVER",
                        "Servo: {}°".format(angle),
                        "Partner: #{}".format(self.partner_sequence),
                        "Me: #{}".format(self.sequence_number)
                    )
                    
                    # Return action to send servo status
                    return {
                        'action': 'send_servo_status',
                        'angle': angle
                    }
                else:
                    print("Failed to move servo")
            else:
                print("Invalid angle type: {} ({})".format(angle, type(angle)))
        else:
            print("No potentiometer_angle found in data")
        
        return None
    
    def _handle_controller_message(self, data):
        """Handle messages for controller device (display servo status)"""
        if 'servo_angle' in data:
            angle = data['servo_angle']
            self.hardware_manager.update_display(
                "CONTROLLER",
                "Remote: {}°".format(angle),
                "Partner: #{}".format(self.partner_sequence),
                "Me: #{}".format(self.sequence_number)
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
                "Knob: {}°".format(angle),
                "Partner: #{}".format(self.partner_sequence),
                "Me: #{}".format(self.sequence_number)
            )
    
    def get_sequence_number(self):
        """Get current sequence number"""
        return self.sequence_number
    
    def get_partner_sequence(self):
        """Get partner sequence number"""
        return self.partner_sequence
