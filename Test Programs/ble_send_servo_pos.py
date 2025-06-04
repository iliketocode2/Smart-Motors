from machine import Pin, SoftI2C, PWM, ADC, Timer
import time
import servo
import ujson  # MicroPython's optimized JSON module

# Servo setup
s = servo.Servo(Pin(2))
servo_angle = 90  # Current servo position

# Sweep parameters (for demo purposes)
sweep_direction = 1
sweep_speed = 2
sweep_min = 0
sweep_max = 180
sweep_delay = 100  # ms between sweep steps
last_sweep_time = 0

def update_servo_position():
    """Update servo position with sweeping motion"""
    global servo_angle, sweep_direction, last_sweep_time
    
    current_time = time.ticks_ms()
    if current_time - last_sweep_time > sweep_delay:
        servo_angle += sweep_direction * sweep_speed
        
        if servo_angle >= sweep_max:
            servo_angle = sweep_max
            sweep_direction = -1
        elif servo_angle <= sweep_min:
            servo_angle = sweep_min
            sweep_direction = 1
        
        last_sweep_time = current_time
        s.write_angle(servo_angle)  # Update physical servo

def grabData():
    """Get current servo position as JSON string"""
    update_servo_position()  # Update position first
    
    message = {
        'x': servo_angle,
        'timestamp': time.ticks_ms(),
        'status': 'OK'
    }
    return ujson.dumps(message)  # Convert dict to JSON string

from BLE_CEEO import Yell, Listen
import time
import json

def callback(data):
        print(data.decode())

def peripheral(name): 
    try:
        print('waiting ...')
        p = Yell(name, interval_us=30000, verbose = False)
        #sensor.skip_frames(time=2000)
        if p.connect_up():
            p.callback = callback
            print('Connected')
            time.sleep(1)
            while p.is_connected:
                p.send(grabData())
                time.sleep(1)
            print('lost connection')
    except Exception as e:
        print('Error: ',e)
    finally:
        p.disconnect()
        print('closing up')
         
peripheral('Maria')
