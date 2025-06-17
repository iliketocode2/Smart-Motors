"""
Hardware abstraction layer for ESP32 SmartMotor components
Handles display, servo, potentiometer, and sensor initialization
"""

from machine import Pin, SoftI2C, ADC
import time
import icons
import servo
import config

class HardwareManager:
    def __init__(self, device_type):
        """Initialize hardware components based on device type"""
        self.device_type = device_type
        self.display = None
        self.servo = None
        self.potentiometer = None
        self.potentiometer_available = False
        
        self._setup_display()
        self._setup_servo()
        self._setup_potentiometer()
        
    def _setup_display(self):
        """Initialize OLED display with error handling"""
        try:
            i2c = SoftI2C(scl=Pin(config.DISPLAY_SCL_PIN), sda=Pin(config.DISPLAY_SDA_PIN))
            self.display = icons.SSD1306_SMART(128, 64, i2c, Pin(config.DISPLAY_RST_PIN))
            self.display.fill(0)
            self.display.text("SmartMotor", 25, 10)
            self.display.text(self.device_type[:10], 25, 25)
            self.display.text("Initializing", 15, 45)
            self.display.show()
            print("Display initialized successfully")
        except Exception as e:
            print("Display initialization failed: {}".format(e))
            self.display = None
    
    def _setup_servo(self):
        """Initialize servo motor for receiver devices"""
        if self.device_type == config.DEVICE_RECEIVER:
            try:
                self.servo = servo.Servo(Pin(config.SERVO_PIN))
                self.servo.write_angle(90)  # Center position
                print("Servo initialized on pin {}".format(config.SERVO_PIN))
            except Exception as e:
                print("Servo initialization failed: {}".format(e))
                self.servo = None
    
    def _setup_potentiometer(self):
        """Initialize potentiometer for controller devices"""
        if self.device_type == config.DEVICE_CONTROLLER:
            try:
                self.potentiometer = ADC(Pin(config.POTENTIOMETER_PIN))
                self.potentiometer.atten(ADC.ATTN_11DB)
                
                # Test potentiometer reading
                test_value = self.potentiometer.read()
                if 0 <= test_value <= 4095:
                    self.potentiometer_available = True
                    print("Potentiometer initialized on pin {}".format(config.POTENTIOMETER_PIN))
                else:
                    print("Potentiometer test failed: {}".format(test_value))
                    self.potentiometer_available = False
                    
            except Exception as e:
                print("Potentiometer initialization failed: {}".format(e))
                self.potentiometer_available = False
                self.potentiometer = None
    
    def update_display(self, line1="SmartMotor", line2="", line3="", line4=""):
        """Update display with status information"""
        if not self.display:
            return
            
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
        except Exception as e:
            print("Display update failed: {}".format(e))
    
    def read_potentiometer(self):
        """Read potentiometer value with smoothing"""
        if not self.potentiometer_available:
            return 90
            
        try:
            # Take multiple readings for stability
            readings = []
            for _ in range(3):
                readings.append(self.potentiometer.read())
                time.sleep_ms(2)
            
            # Average the readings
            avg_reading = sum(readings) / len(readings)
            
            # Convert to angle (0-180 degrees)
            angle = int((180.0 / 4095.0) * avg_reading)
            angle = max(0, min(180, angle))
            
            return angle
            
        except Exception as e:
            print(f"Potentiometer read error: {e}")
            return 90
    
    def move_servo(self, angle):
        """Move servo to specified angle - streamlined for speed"""
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
        """Clean up hardware resources"""
        if self.servo:
            try:
                self.servo.write_angle(90)  # Return to center
            except:
                pass
