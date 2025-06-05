from pyscript import document, window, when
import RS232
import channel
import ble
import plotly

# Initialize components exactly like your original main.py
myRS232 = RS232.CEEO_RS232(divName = 'all_things_rs232', myCSS = True)
myChannel = channel.CEEO_Channel("hackathon", "@chrisrogers", "talking-on-a-channel", divName='all_things_channels', suffix='_bridge')
myBle1 = ble.CEEO_BLE(divName='all_things_ble')  # Controller BLE
myBle2 = ble.CEEO_BLE(divName='all_things_ble')  # Receiver BLE  
myPlot = plotly.CEEO_Plotly(divName='all_things_plotly')

# State management
bridge_active = False
controller_connected = False
receiver_connected = False

def update_ui_status():
    """Update the status displays"""
    try:
        bridge_status = document.getElementById('bridge-status')
        if bridge_status:
            if bridge_active:
                bridge_status.innerHTML = "Bridge Active - Relaying Messages"
            else:
                bridge_status.innerHTML = "Bridge Inactive"
        
        controller_status = document.getElementById('controller-status')
        if controller_status:
            if controller_connected:
                controller_status.innerHTML = "Connected"
                controller_status.className = "status connected"
            else:
                controller_status.innerHTML = "Disconnected"
                controller_status.className = "status disconnected"
                
        receiver_status = document.getElementById('receiver-status')
        if receiver_status:
            if receiver_connected:
                receiver_status.innerHTML = "Connected"
                receiver_status.className = "status connected"
            else:
                receiver_status.innerHTML = "Disconnected"
                receiver_status.className = "status disconnected"
    except Exception as e:
        print(f"UI update error: {e}")

# Controller callback - receives accelerometer data from controller motor
def controller_callback(message):
    global bridge_active
    if not bridge_active:
        return
        
    try:
        # Decode message like in your original code
        data_str = message.decode() if hasattr(message, 'decode') else str(message)
        value = json.loads(data_str)
        
        # Post to channel (like your ContollerChannel.py)
        myChannel.post('/SM/accel', value['value'])
        
        # Update UI display
        controller_data = document.getElementById('controller-data')
        if controller_data:
            controller_data.innerHTML = f"Accel: {value['value']}"
        
        # Update plot
        myPlot.update_chart(value['value'])
        
        print(f"Controller sent: {value['value']}")
        
    except Exception as e:
        print(f"Controller callback error: {e}")

# Channel callback - receives from controller, sends to receiver
def channel_callback(message):
    global bridge_active, receiver_connected
    if not bridge_active or not receiver_connected:
        return
        
    try:
        # Handle message like in your ReceiverChannel.py
        payload = message['payload']
        data = json.loads(payload) if isinstance(payload, str) else payload
        
        if '/SM/accel' in str(data.get('topic', '')):
            # Convert to servo angle (like in ReceiverChannel.py)
            tosend = str(abs(int(data['value'])))
            myBle2.send_str(tosend)
            
            # Update UI
            receiver_data = document.getElementById('receiver-data')
            if receiver_data:
                receiver_data.innerHTML = f"Sent angle: {tosend}"
            
            print(f"Sent to receiver: {tosend}")
            
    except Exception as e:
        print(f"Channel callback error: {e}")

# Receiver callback (optional - for acknowledgments)
def receiver_callback(message):
    try:
        data_str = message.decode() if hasattr(message, 'decode') else str(message)
        print(f"Receiver response: {data_str}")
        
        receiver_data = document.getElementById('receiver-data')
        if receiver_data:
            receiver_data.innerHTML = f"Response: {data_str}"
            
    except Exception as e:
        print(f"Receiver callback error: {e}")

# Set up callbacks (like in your original channel files)
myBle1.callback = controller_callback  # For controller motor
myBle2.callback = receiver_callback    # For receiver motor responses
myChannel.callback = channel_callback  # For channel messages

# Initialize plot (like in your original)
myPlot.initialize(100, 'iteration', 'value', 'SmartMotor Bridge')

# Button event handlers
@when("click", "#start-bridge")
def start_bridge(event):
    global bridge_active
    bridge_active = True
    update_ui_status()
    print("Bridge started - ready to relay messages")

@when("click", "#stop-bridge")
def stop_bridge(event):
    global bridge_active
    bridge_active = False
    update_ui_status()
    print("Bridge stopped")

@when("click", "#connect-controller")
def connect_controller(event):
    global controller_connected
    controller_connected = True
    update_ui_status()
    print("Controller connection enabled")

@when("click", "#disconnect-controller")
def disconnect_controller(event):
    global controller_connected
    controller_connected = False
    update_ui_status()
    print("Controller connection disabled")

@when("click", "#connect-receiver")
def connect_receiver(event):
    global receiver_connected
    receiver_connected = True
    update_ui_status()
    print("Receiver connection enabled")

@when("click", "#disconnect-receiver")
def disconnect_receiver(event):
    global receiver_connected
    receiver_connected = False
    update_ui_status()
    print("Receiver connection disabled")

# Initialize UI
update_ui_status()
print("SmartMotor Bridge initialized")
