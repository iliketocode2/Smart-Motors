from pyscript import document, window, when
import RS232
import channel
import ble
import plotly
import files

# Initialize components exactly like the original
myRS232 = RS232.CEEO_RS232(divName = 'all_things_rs232', myCSS = True)
myChannel = channel.CEEO_Channel("hackathon", "@chrisrogers", "talking-on-a-channel", divName = 'all_things_channels', suffix='_test')
myBle = ble.CEEO_BLE(divName = 'all_things_ble')

import audio, math
sampleRate = 48000
window_size = 0.3
points = int(sampleRate * window_size)
points = 2 ** math.ceil(math.log2(points))
myAudio = audio.CEEO_Audio('all_things_audio', points, sampleRate)

import video
myVideo = video.CEEO_Video('all_things_video')

myPlot = plotly.CEEO_Plotly(divName = 'all_things_plotly')
myFiles = files.CEEO_Files(divName = 'all_things_files')

python_area = document.getElementById('PC_code')

from myCode import generic_code

@when("click", "#loadopenmv")
def on_loadMVcode(event):
    from myCode import openmv_code
    myRS232.python.code = openmv_code + generic_code
    highlight_selected_device("openmv")
    progress_to_step(2)
    
@when("click", "#loadrp2040")
def on_loadRPcode(event):
    from myCode import rp2040_code
    myRS232.python.code = rp2040_code + generic_code
    highlight_selected_device("rp2040")
    progress_to_step(2)
    
@when("click", "#loadspike")
def on_loadSPIKEcode(event):
    from myCode import spike_code
    myRS232.python.code = spike_code + generic_code
    highlight_selected_device("spike")
    progress_to_step(2)
    
@when("click", "#loadesp")
def on_loadESPcode(event):
    from myCode import esp_code
    myRS232.python.code = esp_code + generic_code
    highlight_selected_device("esp32")
    progress_to_step(2)

# Keep original PC code functions exactly the same
@when("click", "#loadte")
def on_loadTEcode(event):
    from myCode import te_code
    python_area.code = te_code 
    
@when("click", "#loaddefault")
def on_loadDefaultcode(event):
    from myCode import default_code
    python_area.code = default_code

# New UI enhancement functions
def highlight_selected_device(device_type):
    """Highlight the selected device card"""
    # Remove highlight from all cards
    cards = document.querySelectorAll('.device-card')
    for card in cards:
        card.style.borderColor = '#e9ecef'
        card.style.backgroundColor = '#f8f9fa'
        card.classList.remove('selected')
    
    # Highlight selected card
    selected_card = document.querySelector(f'[data-device="{device_type}"]')
    if selected_card:
        selected_card.style.borderColor = '#4CAF50'
        selected_card.style.backgroundColor = '#e8f5e8'
        selected_card.classList.add('selected')

def progress_to_step(step_number):
    """Progress to the next step and update UI"""
    # Update sidebar steps
    for i in range(1, 6):
        step_item = document.getElementById(f'step-{i}')
        content_section = document.getElementById(f'content-step-{i}')
        
        if step_item:
            step_item.classList.remove('active', 'completed')
            if i < step_number:
                step_item.classList.add('completed')
            elif i == step_number:
                step_item.classList.add('active')
        
        # Show/hide content sections
        if content_section:
            content_section.classList.remove('active')
            if i == step_number:
                content_section.classList.add('active')
    
    # Scroll to top of main content
    main_content = document.querySelector('.main-content')
    if main_content:
        main_content.scrollTop = 0

# Add manual navigation buttons and better step control
def add_navigation_controls():
    """Add next/back buttons to each step"""
    pass  # Temporarily disable to fix TypeError

# Make show_step_content available globally
def make_navigation_global():
    """Make navigation functions available to onclick handlers"""
    pass  # Temporarily disable to fix TypeError

# Sidebar step click handlers
@when("click", ".step-item")
def on_step_click(event):
    """Handle clicking on sidebar steps"""
    step_item = event.target.closest('.step-item')
    if step_item:
        step_number = int(step_item.getAttribute('data-step'))
        show_step_content(step_number)

def show_step_content(step_number):
    """Show specific step content without automatic progression"""
    # Update sidebar active state
    for i in range(1, 6):
        step_item = document.getElementById(f'step-{i}')
        content_section = document.getElementById(f'content-step-{i}')
        
        if step_item:
            step_item.classList.remove('active')
            if i == step_number:
                step_item.classList.add('active')
        
        # Show/hide content sections
        if content_section:
            content_section.classList.remove('active')
            if i == step_number:
                content_section.classList.add('active')
    
    # Scroll to top of main content
    main_content = document.querySelector('.main-content')
    if main_content:
        main_content.scrollTop = 0

@when("click", "#open-second-tab")
def open_second_tab(event):
    """Open a new tab for connecting a second device"""
    window.open(window.location.href, '_blank')

# Status monitoring functions - keeping original connection logic intact
def update_connection_status():
    """Update the status indicators based on connection states - no logic changes"""
    # Serial status - just update indicator, don't change connection logic
    serial_indicator = document.getElementById('serial-indicator')
    if serial_indicator:
        if hasattr(myRS232, 'connect') and myRS232.connect.innerText == 'disconnect':
            serial_indicator.classList.add('connected')
            serial_indicator.classList.remove('connecting')
        else:
            serial_indicator.classList.remove('connected', 'connecting')
    
    # Bluetooth status - just update indicator, don't change connection logic
    bluetooth_indicator = document.getElementById('bluetooth-indicator')
    if bluetooth_indicator:
        if hasattr(myBle, 'liveBtn') and myBle.liveBtn.style.backgroundColor == 'green':
            bluetooth_indicator.classList.add('connected')
            bluetooth_indicator.classList.remove('connecting')
            # Auto-advance to Channel step when Bluetooth is actually connected
            if not hasattr(update_connection_status, 'bluetooth_was_connected'):
                progress_to_step(4)
                update_connection_status.bluetooth_was_connected = True
        else:
            bluetooth_indicator.classList.remove('connected', 'connecting')
    
    # Channel status - just update indicator, don't change connection logic
    channel_indicator = document.getElementById('channel-indicator')
    if channel_indicator:
        if hasattr(c_btn) and c_btn.innerText == 'disconnect':
            channel_indicator.classList.add('connected')
            channel_indicator.classList.remove('connecting')
            # Auto-advance to Monitoring step when Channel is connected
            if not hasattr(update_connection_status, 'channel_was_connected'):
                progress_to_step(5)
                update_connection_status.channel_was_connected = True
        else:
            channel_indicator.classList.remove('connected', 'connecting')

# Set up periodic status updates
def setup_status_monitoring():
    """Set up periodic monitoring of connection status"""
    window.setInterval(update_connection_status, 1000)  # Check every second

# Initialize default code and start monitoring
on_loadDefaultcode(None)
setup_status_monitoring()
add_navigation_controls()
make_navigation_global()
