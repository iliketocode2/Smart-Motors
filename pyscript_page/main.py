from pyscript import document, window, when
import RS232
import channel
import ble
import json

# Initialize components
myRS232 = RS232.CEEO_RS232(divName='all_things_rs232', myCSS=True)
myChannel = channel.CEEO_Channel("hackathon", "@chrisrogers", "talking-on-a-channel", 
                                divName='all_things_channels', suffix='_monitor')
myBle = ble.CEEO_BLE(divName='all_things_ble')

# Channel monitoring state
channel_state = {
    'active': False,
    'messages_seen': 0,
    'controller_messages': 0,
    'receiver_responses': 0
}

def log_message(msg):
    """Helper to log messages"""
    print(f"[MONITOR] {msg}")

def update_ui_status():
    """Update status display on the page"""
    try:
        status_div = document.getElementById('channel_status')
        if status_div:
            if channel_state['active']:
                status_div.innerHTML = f"""
                    <h3>Channel Status: MONITORING</h3>
                    <p>Total messages: {channel_state['messages_seen']}</p>
                    <p>Controller data: {channel_state['controller_messages']}</p>
                    <p>Receiver responses: {channel_state['receiver_responses']}</p>
                """
            else:
                status_div.innerHTML = "<h3>Channel Status: INACTIVE</h3>"
    except:
        pass

def handle_channel_message(message):
    """Monitor all messages on the WebSocket channel"""
    if not channel_state['active']:
        return
        
    try:
        payload = message.get('payload', {})
        topic = payload.get('topic', '')
        value = payload.get('value', '')
        
        channel_state['messages_seen'] += 1
        
        # Log different types of messages
        if '/SM/accel' in topic:
            channel_state['controller_messages'] += 1
            log_message(f"Controller sent accelerometer: {value}")
            
        elif '/SM/servo' in topic:
            channel_state['receiver_responses'] += 1
            log_message(f"Receiver servo response: {value}")
            
        else:
            log_message(f"Other message - topic: {topic}, value: {value}")
        
        # Update UI display
        try:
            message_log = document.getElementById('message_log')
            if message_log:
                current_log = message_log.innerHTML
                new_entry = f"<div>Topic: {topic} | Value: {value}</div>"
                # Keep only last 10 messages
                lines = current_log.split('<div>')
                if len(lines) > 10:
                    lines = lines[-9:]  # Keep last 9 + new one = 10
                message_log.innerHTML = '<div>'.join(lines) + new_entry
        except:
            pass
            
        update_ui_status()
        
    except Exception as e:
        log_message(f"Channel monitor error: {e}")

def handle_ble_message(message):
    """Handle BLE for local testing/debugging"""
    try:
        data_str = message.decode() if hasattr(message, 'decode') else str(message)
        log_message(f"BLE received (local test): {data_str}")
        
        # If this is test data, post it to channel
        try:
            data = json.loads(data_str)
            if 'topic' in data and 'value' in data:
                myChannel.post(data['topic'], data['value'])
                log_message(f"Posted test data to channel: {data['topic']} = {data['value']}")
        except:
            # Treat as raw accelerometer data for testing
            myChannel.post('/SM/accel', data_str)
            log_message(f"Posted raw test data: {data_str}")
            
    except Exception as e:
        log_message(f"BLE handler error: {e}")

# Set up monitoring
myChannel.callback = handle_channel_message
myBle.callback = handle_ble_message

# Button handlers
@when("click", "#start_monitor")
def start_monitor(event):
    channel_state['active'] = True
    log_message("Channel monitoring STARTED")
    update_ui_status()

@when("click", "#stop_monitor")
def stop_monitor(event):
    channel_state['active'] = False
    log_message("Channel monitoring STOPPED")
    update_ui_status()

@when("click", "#reset_counters")
def reset_counters(event):
    channel_state['messages_seen'] = 0
    channel_state['controller_messages'] = 0
    channel_state['receiver_responses'] = 0
    log_message("Counters reset")
    update_ui_status()
    # Clear message log
    try:
        message_log = document.getElementById('message_log')
        if message_log:
            message_log.innerHTML = ""
    except:
        pass

@when("click", "#send_test_command")
def send_test_command(event):
    """Send a test servo command through the channel"""
    try:
        test_angle = 90  # Test servo angle
        myChannel.post('/SM/servo_cmd', test_angle)
        log_message(f"Sent test servo command: {test_angle} degrees")
    except Exception as e:
        log_message(f"Error sending test command: {e}")

@when("click", "#clear_log")
def clear_log(event):
    try:
        message_log = document.getElementById('message_log')
        if message_log:
            message_log.innerHTML = ""
        log_message("Message log cleared")
    except:
        pass

# Initialize
log_message("SmartMotor WebSocket Channel Monitor Ready!")
log_message("")
log_message("SETUP INSTRUCTIONS:")
log_message("1. Program your ESP32 SmartMotors to connect to WiFi")
log_message("2. Controller ESP32 connects to: wss://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon")
log_message("3. Receiver ESP32 connects to the same WebSocket URL")
log_message("4. Controller posts accelerometer data to topic '/SM/accel'")
log_message("5. Receiver listens for '/SM/accel' and moves servo accordingly")
log_message("6. This PyScript page monitors the channel traffic")
log_message("")
log_message("WebSocket URL for ESP32 code:")
log_message("wss://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon")
log_message("")
log_message("Click 'Start Monitor' to begin watching channel traffic!")

# Initialize UI
update_ui_status()
