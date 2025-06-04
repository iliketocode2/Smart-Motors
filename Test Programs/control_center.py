from machine import Pin, SoftI2C, PWM, ADC, Timer
import time
import servo
import icons

# Debug control - set to False to reduce terminal output
DEBUG = False

# Hardware setup
i2c = SoftI2C(scl = Pin(7), sda = Pin(6))
display = icons.SSD1306_SMART(128, 64, i2c, Pin(10))

# Servo setup
s = servo.Servo(Pin(2))

# Button setup
switch_down = Pin(8, Pin.IN)
switch_select = Pin(9, Pin.IN)
switch_up = Pin(10, Pin.IN)

# Knob (potentiometer) setup - using the correct pin from sensors.py
knob_available = False
knob = None

try:
    knob = ADC(Pin(3))  # Pin 3 as per sensors.py
    knob.atten(ADC.ATTN_11DB)  # Full range 0-3.3V
    # Test read to see if it works
    test_read = knob.read()
    if 0 <= test_read <= 4095:  # Valid ADC range
        knob_available = True
        if DEBUG:
            print(f"Knob initialized on Pin 3")
            print(f"Initial knob reading: {test_read}")
    else:
        if DEBUG:
            print(f"Knob reading out of range: {test_read}")
except Exception as e:
    if DEBUG:
        print(f"Knob initialization failed: {e}")

if not knob_available and DEBUG:
    print("Warning: Knob not available - check pin 3 connection")

# Control modes
modes = ["KNOB", "MANUAL", "SWEEP", "PATTERN"]
current_mode = 0
servo_angle = 90  # Current servo position

# Manual control variables
manual_angle = 90
angle_step = 5

# Sweep mode variables
sweep_direction = 1
sweep_speed = 2
sweep_min = 0
sweep_max = 180
last_sweep_time = 0
sweep_delay = 100  # ms between sweep steps

# Pattern mode variables
pattern_step = 0
pattern_positions = [0, 45, 90, 135, 180, 135, 90, 45]  # Predefined pattern
pattern_delay = 1000  # ms between moves
last_pattern_time = 0

# Button state tracking (following your main.py pattern)
switch_state_up = False
switch_state_down = False
switch_state_select = False
last_switch_state_up = False
last_switch_state_down = False
last_switch_state_select = False
switched_up = False
switched_down = False
switched_select = False
last_pressed = 0

# Display variables
last_display_update = 0
display_update_interval = 100  # Update display every 100ms

# Servo control variables (key addition from your main.py)
oldpoint = [-1, -1]
current_point = [0, 90]  # [sensor_value, angle]

# Knob filtering and calibration variables - using sensors.py approach
knob_readings = []  # Store readings for averaging like sensors.py
knob_sample_size = 30  # Take 30 samples like sensors.py (reduced from 100 for responsiveness)
knob_last_stable_angle = 90  # Last stable angle reading
knob_dead_zone = 2    # Small dead zone to prevent micro-jitter

def check_switch(p):
    """Handle button state changes with debouncing - following your main.py pattern exactly"""
    global switch_state_up, switch_state_down, switch_state_select
    global switched_up, switched_down, switched_select
    global last_switch_state_up, last_switch_state_down, last_switch_state_select
    
    switch_state_up = switch_up.value()
    switch_state_down = switch_down.value()
    switch_state_select = switch_select.value()
         
    if switch_state_up != last_switch_state_up:
        switched_up = True
    elif switch_state_down != last_switch_state_down:
        switched_down = True
    elif switch_state_select != last_switch_state_select:
        switched_select = True
                
    if switched_up:
        if switch_state_up == 0:
            handle_up_button()
        switched_up = False
    elif switched_down:
        if switch_state_down == 0:
            handle_down_button()
        switched_down = False
    elif switched_select:
        if switch_state_select == 0:
            handle_select_button()
        switched_select = False
    
    last_switch_state_up = switch_state_up
    last_switch_state_down = switch_state_down
    last_switch_state_select = switch_state_select

def handle_up_button():
    """Handle up button - depends on current mode"""
    global current_mode, manual_angle, sweep_max, angle_step, last_pressed
    global knob_dead_zone, knob_sample_size
    
    if time.ticks_ms() - last_pressed < 200:  # Debounce like in main.py
        return
    last_pressed = time.ticks_ms()
    
    if DEBUG:
        print(f"UP pressed in mode: {modes[current_mode]}")
    
    if modes[current_mode] == "MANUAL":
        manual_angle = min(180, manual_angle + angle_step)
        if DEBUG:
            print(f"Manual angle: {manual_angle}")
    elif modes[current_mode] == "SWEEP":
        sweep_max = min(180, sweep_max + 15)
        if DEBUG:
            print(f"Sweep max: {sweep_max}")
    elif modes[current_mode] == "KNOB":
        # Adjust knob responsiveness by changing sample size
        knob_sample_size = min(50, knob_sample_size + 5)
        if DEBUG:
            print(f"Knob smoothing increased (samples: {knob_sample_size})")
    elif modes[current_mode] == "PATTERN":
        # Skip to next pattern step
        global pattern_step
        pattern_step = (pattern_step + 1) % len(pattern_positions)

def handle_down_button():
    """Handle down button - depends on current mode"""
    global current_mode, manual_angle, sweep_min, angle_step, last_pressed
    global knob_dead_zone, knob_sample_size
    
    if time.ticks_ms() - last_pressed < 200:  # Debounce
        return
    last_pressed = time.ticks_ms()
    
    if DEBUG:
        print(f"DOWN pressed in mode: {modes[current_mode]}")
    
    if modes[current_mode] == "MANUAL":
        manual_angle = max(0, manual_angle - angle_step)
        if DEBUG:
            print(f"Manual angle: {manual_angle}")
    elif modes[current_mode] == "SWEEP":
        sweep_min = max(0, sweep_min - 15)
        if DEBUG:
            print(f"Sweep min: {sweep_min}")
    elif modes[current_mode] == "KNOB":
        # Adjust knob responsiveness by changing sample size
        knob_sample_size = max(5, knob_sample_size - 5)
        if DEBUG:
            print(f"Knob smoothing decreased (samples: {knob_sample_size})")
    elif modes[current_mode] == "PATTERN":
        # Go to previous pattern step
        global pattern_step
        pattern_step = (pattern_step - 1) % len(pattern_positions)

def handle_select_button():
    """Handle select button - cycle through modes"""
    global current_mode, last_pressed
    
    if time.ticks_ms() - last_pressed < 200:  # Debounce
        return
    last_pressed = time.ticks_ms()
    
    current_mode = (current_mode + 1) % len(modes)
    if DEBUG:
        print(f"Switched to mode: {modes[current_mode]}")

def read_knob_smooth():
    """Read knob position using sensors.py method with averaging and outlier rejection"""
    global knob_readings, knob_sample_size, knob_dead_zone, knob_last_stable_angle
    
    if not knob_available:
        return 90  # Default center position
    
    try:
        # Collect multiple readings like in sensors.py
        readings = []
        for i in range(knob_sample_size):
            raw_value = knob.read()
            readings.append(raw_value)
        
        # Sort and take middle values to remove outliers (like sensors.py)
        readings.sort()
        middle_start = knob_sample_size // 4
        middle_end = 3 * knob_sample_size // 4
        if middle_end > middle_start:
            middle_readings = readings[middle_start:middle_end]
        else:
            middle_readings = readings
        
        # Calculate average of middle readings
        average_raw = sum(middle_readings) / len(middle_readings)
        
        # Map from ADC range (0-4095) to servo angle (0-180) like sensors.py mappot function
        # This is the inverse of sensors.py mapping: 
        # angle = (180-0) / (4095-0) * (value - 0) + 0
        angle = int((180.0 / 4095.0) * average_raw)
        
        # Clamp to valid servo range
        angle = max(0, min(180, angle))
        
        # Apply dead zone to prevent small jitter
        if abs(angle - knob_last_stable_angle) > knob_dead_zone:
            knob_last_stable_angle = angle
            if DEBUG:
                print(f"KNOB: Raw_avg={average_raw:.1f} -> Angle={angle}° (samples: {len(middle_readings)})")
        
        # Debug: Print occasionally
        if DEBUG and time.ticks_ms() % 3000 < 50:  # Every 3 seconds
            print(f"KNOB DEBUG: Raw_range={min(readings)}-{max(readings)}, Avg={average_raw:.1f}, Angle={angle}°")
        
        return knob_last_stable_angle
        
    except Exception as e:
        if DEBUG:
            print(f"Knob read error: {e}")
        return knob_last_stable_angle  # Return last known good value

def update_servo():
    """Update servo position based on current mode - following main.py servo pattern"""
    global servo_angle, current_point, oldpoint
    global sweep_direction, pattern_step, last_pattern_time, last_sweep_time
    
    current_time = time.ticks_ms()
    new_angle = servo_angle  # Start with current angle
    
    # Determine target angle based on mode
    if modes[current_mode] == "KNOB":
        # Direct knob control with improved smoothing
        new_angle = read_knob_smooth()
        
    elif modes[current_mode] == "MANUAL":
        # Button-controlled manual positioning
        new_angle = manual_angle
        
    elif modes[current_mode] == "SWEEP":
        # Automatic sweeping motion
        if current_time - last_sweep_time > sweep_delay:
            new_angle += sweep_direction * sweep_speed
            
            if new_angle >= sweep_max:
                new_angle = sweep_max
                sweep_direction = -1
            elif new_angle <= sweep_min:
                new_angle = sweep_min
                sweep_direction = 1
            
            last_sweep_time = current_time
            
    elif modes[current_mode] == "PATTERN":
        # Follow predefined pattern
        if current_time - last_pattern_time > pattern_delay:
            new_angle = pattern_positions[pattern_step]
            pattern_step = (pattern_step + 1) % len(pattern_positions)
            last_pattern_time = current_time
    
    # Constrain angle to valid range
    new_angle = max(0, min(180, new_angle))
    
    # Update current point (following main.py pattern)
    current_point = [0, new_angle]  # [sensor_value, angle]
    
    # Only move servo when point changes significantly (following main.py logic)
    # Use different thresholds for different modes
    if modes[current_mode] == "KNOB":
        angle_threshold = 3  # Larger threshold for knob to reduce jitter
    else:
        angle_threshold = 0
    
    if abs(current_point[1] - oldpoint[1]) > angle_threshold or not current_point == oldpoint:
        try:
            s.write_angle(current_point[1])  # Use the angle from current_point
            servo_angle = current_point[1]
            
            # Print servo movements
            if DEBUG:
                if modes[current_mode] == "KNOB":
                    print(f"SERVO: {oldpoint[1]}° -> {servo_angle}°")
                elif abs(current_point[1] - oldpoint[1]) > 5:
                    print(f"Servo moved to: {servo_angle}° (mode: {modes[current_mode]})")
                
        except Exception as e:
            if DEBUG:
                print(f"Servo error: {e}")
        
        oldpoint = current_point[:]  # Update oldpoint

def update_display():
    """Update the display with current status"""
    global last_display_update
    
    current_time = time.ticks_ms()
    if current_time - last_display_update < display_update_interval:
        return
    
    last_display_update = current_time
    
    display.fill(0)
    
    # Title and mode
    display.text("SERVO CONTROL", 15, 0)
    display.text(f"Mode: {modes[current_mode]}", 5, 12)
    
    # Current angle display
    display.text(f"Angle: {servo_angle}°", 5, 24)
    
    # Mode-specific info
    if modes[current_mode] == "KNOB":
        if knob_available:
            display.text(f"Knob: {knob_last_stable_angle}°", 70, 24)
            display.text(f"Samples: {knob_sample_size}", 5, 36)
            display.text(f"DZ: {knob_dead_zone}", 70, 36)
        else:
            display.text("Knob: N/A", 70, 24)
            display.text("Knob not detected", 5, 36)
        
    elif modes[current_mode] == "MANUAL":
        display.text(f"Target: {manual_angle}°", 70, 24)
        display.text("UP/DOWN: Adjust", 5, 36)
        display.text(f"Step: {angle_step}°", 5, 46)
        
    elif modes[current_mode] == "SWEEP":
        display.text(f"Range:{sweep_min}-{sweep_max}", 60, 24)
        display.text("Auto sweeping", 5, 36)
        display.text("UP/DN: Range", 5, 46)
        
    elif modes[current_mode] == "PATTERN":
        display.text(f"Step: {pattern_step}", 70, 24)
        display.text("Following pattern", 5, 36)
        next_pos = pattern_positions[pattern_step]
        display.text(f"Next: {next_pos}°", 5, 46)
    
    # Controls
    display.text("SELECT: Mode", 5, 56)
    
    # Visual angle indicator (simple bar)
    bar_width = int((servo_angle / 180.0) * 100)
    for i in range(bar_width):
        display.pixel(14 + i, 50, 1)
    display.text("|", 10, 47)
    display.text("|", 118, 47)
    
    display.show()

def display_startup():
    """Show startup animation"""
    display.fill(0)
    display.text("SmartMotor", 25, 15)
    display.text("Servo Control", 18, 25)
    display.text("Center", 42, 35)
    display.text("Initializing...", 20, 50)
    display.show()
    
    # Move servo to center position like in main.py
    if DEBUG:
        print("Centering servo...")
    s.write_angle(90)
    servo_angle = 90
    current_point = [0, 90]
    oldpoint = [0, 90]
    
    time.sleep(1)

# Initialize hardware using Timer like in main.py
tim = Timer(0)
tim.init(period=50, mode=Timer.PERIODIC, callback=check_switch)

# Startup sequence
display_startup()

if DEBUG:
    print("SmartMotor Servo Control Center Started!")
    print("Controls:")
    print("- SELECT: Change mode (KNOB/MANUAL/SWEEP/PATTERN)")
    print("- UP/DOWN: Adjust parameters based on mode")
    if knob_available:
        print("- Knob: Direct servo control in KNOB mode (Pin 3)")
        print("- UP/DOWN in KNOB mode: Adjust smoothing")
    else:
        print("- Knob: Not detected - check Pin 3 wiring")

# Main control loop - following main.py pattern
while True:
    try:
        update_servo()
        update_display()
        time.sleep(0.02)  # Small delay for smooth operation
        
    except KeyboardInterrupt:
        if DEBUG:
            print("Shutting down...")
        s.write_angle(90)  # Return to center
        break
    except Exception as e:
        if DEBUG:
            print(f"Error: {e}")
        time.sleep(1)
