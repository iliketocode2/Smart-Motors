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
        
        # Set up topics based on device type - FIXED ROUTING
        if device_type == config.DEVICE_CONTROLLER:
            self.send_topic = "/controller/status"
            self.listen_topic = "/receiver/status"  # Controller listens for receiver status
        else:  # DEVICE_RECEIVER
            self.send_topic = "/receiver/status"  
            self.listen_topic = "/controller/status"  # Receiver listens for controller status
        
        print("Device: {} | Send: {} | Listen: {}".format(
            device_type, self.send_topic, self.listen_topic))
    
    def create_data_message(self, angle):
        """Create simple data message - just topic and angle"""
        self.sequence_number += 1
        
        return {
            "topic": self.send_topic,
            "value": int(angle)
        }
    
    def create_heartbeat_message(self):
        """Create simple heartbeat - just topic and sequence"""
        self.sequence_number += 1
        
        return {
            "topic": self.send_topic,
            "value": "heartbeat"
        }
    
    def process_received_message(self, message_data):
        """Process simplified messages - both fragments and complete"""
        try:
            # Handle fragment messages (dict format)
            if isinstance(message_data, dict):
                if message_data.get('type') == 'fragment':
                    topic = message_data.get('topic', '')
                    
                    if topic == self.listen_topic:
                        if self.device_type == config.DEVICE_RECEIVER and 'potentiometer_angle' in message_data:
                            angle = message_data['potentiometer_angle']
                            return self._process_servo_control(angle)
                        elif self.device_type == config.DEVICE_CONTROLLER and 'servo_angle' in message_data:
                            angle = message_data['servo_angle']
                            self._update_controller_display(angle)
                    
                return None
            
            # Handle complete JSON messages - now much simpler
            channel_msg = json.loads(message_data)
            
            if channel_msg.get('type') == 'welcome':
                print("Channel connected")
                return None
            
            # Handle CEEO channel data messages
            if channel_msg.get('type') == 'data' and 'payload' in channel_msg:
                payload_str = channel_msg['payload']
                payload = json.loads(payload_str)
                
                topic = payload.get('topic', '')
                value = payload.get('value')
                
                print("Msg: {} = {}".format(topic, value))
                
                # Check if message is for this device
                if topic == self.listen_topic:
                    if isinstance(value, (int, float)):
                        # It's an angle value
                        if self.device_type == config.DEVICE_RECEIVER:
                            return self._process_servo_control(int(value))
                        else:
                            self._update_controller_display(int(value))
                    elif value == "heartbeat":
                        print("Partner heartbeat")
                    
        except Exception as e:
            print("Message error: {}".format(e))
        
        return None
    
    def _process_servo_control(self, angle):
        """Move servo to angle and send confirmation"""
        if isinstance(angle, (int, float)):
            angle = max(0, min(180, int(angle)))
            
            if self.hardware_manager.move_servo(angle):
                self.current_servo_angle = angle
                
                # Update display
                self.hardware_manager.update_display(
                    "RECEIVER",
                    "Servo: {}°".format(angle),
                    "Seq: #{}".format(self.sequence_number),
                    "Connected"
                )
                
                # Send confirmation
                return {
                    'action': 'send_confirmation',
                    'angle': angle
                }
        
        return None
    
    def _update_controller_display(self, angle):
        """Update controller display with confirmed servo angle"""
        self.hardware_manager.update_display(
            "CONTROLLER",
            "Remote: {}°".format(angle),
            "Seq: #{}".format(self.sequence_number), 
            "Connected"
        )
    
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
        """Handle messages for receiver device - optimized for speed"""
        if 'potentiometer_angle' in data:
            angle = data['potentiometer_angle']
            
            if isinstance(angle, (int, float)):
                angle = max(0, min(180, int(angle)))
                
                # Move servo and update display - remove verbose logging
                if self.hardware_manager.move_servo(angle):
                    self.current_servo_angle = angle
                    
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
