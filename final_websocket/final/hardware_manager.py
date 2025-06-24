"""
Hardware abstraction layer for ESP32 SmartMotor components
- Cached values to reduce hardware access
"""

from machine import Pin, SoftI2C, ADC
import time
import icons
import servo
import config

class HardwareManager:
    def __init__(self, device_type):
        self.device_type = device_type
        self.display = None
        self.servo = None
        self.potentiometer = None
        self.potentiometer_available = False
        
        # Cache hardware values to reduce access frequency
        self.cached_potentiometer_value = 90
        self.last_potentiometer_read = 0
        self.potentiometer_cache_timeout = 20  # Cache for 20ms
        
        # Pre-allocate display strings to reduce memory
        self.display_line1 = ""
        self.display_line2 = ""
        self.display_line3 = ""
        self.display_line4 = ""
        
        self._setup_display()
        self._setup_servo()
        self._setup_potentiometer()
        
    def _setup_display(self):
        """Initialize OLED display"""
        try:
            i2c = SoftI2C(scl=Pin(config.DISPLAY_SCL_PIN), sda=Pin(config.DISPLAY_SDA_PIN))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(config.DISPLAY_RST_PIN))
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 10)
            self.display.text(self.device_type[:10], 25, 25)
            self.display.text("Optimized", 20, 45)
            self.display.show()
            print("Display initialized successfully")
        except Exception as e:
            print("Display initialization failed: {}".format(e))
            self.display = None
    
    def _setup_servo(self):
        """Initialize servo motor - same logic"""
        if self.device_type == config.DEVICE_RECEIVER:
            try:
                self.servo = servo.Servo(Pin(config.SERVO_PIN))
                self.servo.write_angle(90)  # Center position
                print("Servo initialized on pin {}".format(config.SERVO_PIN))
            except Exception as e:
                print("Servo initialization failed: {}".format(e))
                self.servo = None
    
    def _setup_potentiometer(self):
        """Initialize potentiometer - same logic"""
        if self.device_type == config.DEVICE_CONTROLLER:
            try:
                self.potentiometer = ADC(Pin(config.POTENTIOMETER_PIN))
                self.potentiometer.atten(ADC.ATTN_11DB)
                
                # Test potentiometer reading
                test_value = self.potentiometer.read()
                if 0 <= test_value <= 4095:
                    self.potentiometer_available = True
                    # Initialize cache with first reading
                    self.cached_potentiometer_value = int((180.0 / 4095.0) * test_value)
                    print("Potentiometer initialized on pin {}".format(config.POTENTIOMETER_PIN))
                else:
                    print("Potentiometer test failed: {}".format(test_value))
                    self.potentiometer_available = False
                    
            except Exception as e:
                print("Potentiometer initialization failed: {}".format(e))
                self.potentiometer_available = False
                self.potentiometer = None
    
    def update_display(self, line1="SmartMotor", line2="", line3="", line4=""):
        """OPTIMIZED: Update display only when content changes"""
        if not self.display:
            return
        
        # Only update display if content actually changed
        if (line1 == self.display_line1 and line2 == self.display_line2 and 
            line3 == self.display_line3 and line4 == self.display_line4):
            return  # No change, skip expensive display update
            
        try:
            self.display.fill(0)
            self.display.text(line1[:16], 0, 10)
            if line2:
                self.display.text(line2[:16], 0, 25)
            if line3:
                self.display.text(line3[:16], 0, 40)
            if line4:
                self.display.text(line4[:16], 0, 55)
            self.display.show()
            
            # Cache the displayed content
            self.display_line1 = line1
            self.display_line2 = line2
            self.display_line3 = line3
            self.display_line4 = line4
            
        except Exception as e:
            print("Display update failed: {}".format(e))
    
    def read_potentiometer(self):
        """OPTIMIZED: Read potentiometer with caching and faster sampling"""
        if not self.potentiometer_available:
            return 90
        
        current_time = time.ticks_ms()
        
        # Use cached value if recent reading is available
        if time.ticks_diff(current_time, self.last_potentiometer_read) < self.potentiometer_cache_timeout:
            return self.cached_potentiometer_value
            
        try:
            reading = self.potentiometer.read()
            
            # Convert to angle (0-180 degrees)
            angle = int((180.0 / 4095.0) * reading)
            angle = max(0, min(180, angle))
            
            # Update cache
            self.cached_potentiometer_value = angle
            self.last_potentiometer_read = current_time
            
            return angle
            
        except Exception as e:
            print(f"Potentiometer read error: {e}")
            return self.cached_potentiometer_value  # Return cached value on error
    
    def read_potentiometer_fast(self):
        """OPTIMIZATION 7: Ultra-fast potentiometer reading for high-frequency polling"""
        if not self.potentiometer_available:
            return 90
            
        try:
            # Single raw read, no error checking for maximum speed
            reading = self.potentiometer.read()
            angle = int((180.0 / 4095.0) * reading)
            return max(0, min(180, angle))
        except:
            return self.cached_potentiometer_value
    
    def move_servo(self, angle):
        """OPTIMIZED: Streamlined servo movement"""
        if not self.servo:
            return False
            
        try:
            angle = max(0, min(180, int(angle)))
            self.servo.write_angle(angle)
            return True
        except Exception as e:
            print("Servo movement error: {}".format(e))
            return False
    
    def cleanup(self):
        """Clean up hardware resources - optimized"""
        if self.servo:
            try:
                self.servo.write_angle(90)  # Return to center
            except:
                pass
        
        # Clear display cache
        self.display_line1 = ""
        self.display_line2 = ""
        self.display_line3 = ""
        self.display_line4 = ""
