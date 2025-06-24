"""
Message handling UPDATED to use config values
Partner timeout and other timing values now come from config.py
"""

import json
import time
import config

class MessageHandler:
    def __init__(self, device_type, hardware_manager):
        """Initialize message handler using config values"""
        self.device_type = device_type
        self.hardware_manager = hardware_manager
        self.sequence_number = 0
        self.partner_sequence = 0
        
        # State tracking for persistence
        self.last_angle_sent = 90
        self.current_servo_angle = 90
        self.last_confirmed_angle = 90
        self.partner_last_seen = time.ticks_ms()
        self.channel_welcomed = False
        
        # Connection health tracking
        self.last_message_received = 0
        self.partner_alive = False
        self.reconnection_count = 0
        
        # Set up topics based on device type
        if device_type == config.DEVICE_CONTROLLER:
            self.send_topic = "/controller/data"
            self.listen_topic = "/receiver/data"
        else:  # DEVICE_RECEIVER
            self.send_topic = "/receiver/data"
            self.listen_topic = "/controller/data"
        
        print("Device: {} | Send: {} | Listen: {}".format(
            device_type, self.send_topic, self.listen_topic))
    
    def create_data_message(self, angle):
        """Create data message with state tracking"""
        self.sequence_number += 1
        
        # Track the angle we're sending
        if self.device_type == config.DEVICE_CONTROLLER:
            self.last_angle_sent = angle
        else:
            self.current_servo_angle = angle
        
        return {
            "topic": self.send_topic,
            "value": int(angle)
        }
    
    def create_heartbeat_message(self):
        """Create heartbeat message"""
        self.sequence_number += 1
        
        return {
            "topic": self.send_topic,
            "value": "heartbeat"
        }
    
    def process_received_message(self, message_data):
        """Process messages with CEEO channel awareness"""
        try:
            # Handle fragment messages (dict format)
            if isinstance(message_data, dict):
                return self._handle_fragment_message(message_data)
            
            # Handle complete JSON messages (CEEO channel format)
            try:
                channel_msg = json.loads(message_data)
            except (ValueError, TypeError):
                return None
            
            # Handle CEEO channel welcome message
            if channel_msg.get('type') == 'welcome':
                print("CEEO Channel welcomed - connection established")
                self.channel_welcomed = True
                self.reconnection_count += 1
                
                self.hardware_manager.update_display(
                    "SmartMotor",
                    "Channel Ready",
                    "Conn #{}".format(self.reconnection_count),
                    "Waiting..."
                )
                return {'action': 'channel_welcome'}
            
            # Handle CEEO channel data messages
            if channel_msg.get('type') == 'data' and 'payload' in channel_msg:
                return self._handle_ceeo_data_message(channel_msg)
                
        except Exception as e:
            print("Message processing error: {}".format(e))
        
        return None
    
    def _handle_fragment_message(self, message_data):
        """Handle fragment messages"""
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
    
    def _handle_ceeo_data_message(self, channel_msg):
        """Handle CEEO channel data messages"""
        try:
            payload_str = channel_msg['payload']
            payload = json.loads(payload_str)
        except (ValueError, TypeError):
            return None
        
        topic = payload.get('topic', '')
        value = payload.get('value')
        
        print("Msg: {} = {}".format(topic, value))
        
        # Update partner activity tracking
        self.last_message_received = time.ticks_ms()
        self.partner_alive = True
        self.partner_last_seen = time.ticks_ms()
        
        # Check if message is for this device
        if topic == self.listen_topic:
            if isinstance(value, (int, float)):
                angle_val = int(value)
                
                if self.device_type == config.DEVICE_RECEIVER:
                    return self._process_servo_control(angle_val)
                else:
                    self._update_controller_display(angle_val)
                    
            elif value == "heartbeat":
                print("Partner heartbeat")
                self._update_partner_heartbeat_display()
        
        return None
    
    def _process_servo_control(self, angle):
        """Process servo control with state tracking"""
        if not isinstance(angle, (int, float)):
            return None
        
        angle = max(0, min(180, int(angle)))
        
        # Check if this is a significant change
        angle_change = abs(angle - self.current_servo_angle)
        
        if angle_change >= config.ANGLE_CHANGE_THRESHOLD:
            if self.hardware_manager.move_servo(angle):
                self.current_servo_angle = angle
                self.last_confirmed_angle = angle
                
                # Update display
                self.hardware_manager.update_display(
                    "RECEIVER",
                    "Servo: {}deg".format(angle),
                    "Partner: Active" if self.partner_alive else "Partner: Lost",
                    "Seq: #{}".format(self.sequence_number)
                )
                
                # Send confirmation
                return {
                    'action': 'send_confirmation',
                    'angle': angle
                }
        
        return None
    
    def _update_controller_display(self, angle):
        """Update controller display"""
        self.last_confirmed_angle = angle
        
        status = "Connected" if self.partner_alive else "Lost"
        
        self.hardware_manager.update_display(
            "CONTROLLER",
            "Remote: {}deg".format(angle),
            "Status: {}".format(status),
            "Seq: #{}".format(self.sequence_number)
        )
    
    def _update_partner_heartbeat_display(self):
        """Update display when partner heartbeat is received"""
        if self.device_type == config.DEVICE_CONTROLLER:
            self.hardware_manager.update_display(
                "CONTROLLER",
                "Remote: {}deg".format(self.last_confirmed_angle),
                "Partner: Alive",
                "Last HB: Now"
            )
        else:
            self.hardware_manager.update_display(
                "RECEIVER",
                "Servo: {}deg".format(self.current_servo_angle),
                "Partner: Alive", 
                "Last HB: Now"
            )
    
    def should_send_potentiometer_data(self):
        """Check if controller should send potentiometer data using config values"""
        if self.device_type != config.DEVICE_CONTROLLER:
            return False, 0
        
        current_angle = self.hardware_manager.read_potentiometer()
        
        # Check if angle changed significantly OR if partner might be stale
        angle_change = abs(current_angle - self.last_angle_sent)
        time_since_partner = time.ticks_diff(time.ticks_ms(), self.partner_last_seen)
        
        # Send if significant change OR if we haven't heard from partner recently
        if angle_change >= config.ANGLE_CHANGE_THRESHOLD or time_since_partner > config.PARTNER_TIMEOUT_MS:
            self.last_angle_sent = current_angle
            return True, current_angle
        
        return False, current_angle
    
    def is_partner_alive(self):
        """Check if partner is still alive using config timeout"""
        time_since_last = time.ticks_diff(time.ticks_ms(), self.partner_last_seen)
        self.partner_alive = time_since_last < config.PARTNER_TIMEOUT_MS
        return self.partner_alive
    
    def on_reconnection(self):
        """Handle reconnection event"""
        print("Message handler: Handling reconnection")
        self.channel_welcomed = False
        self.partner_alive = False
        self.reconnection_count += 1
        
        self.hardware_manager.update_display(
            "SmartMotor",
            "Reconnecting...",
            "Attempt #{}".format(self.reconnection_count),
            "Please wait"
        )
