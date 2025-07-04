"""
Boot script for ESP32 SmartMotor
Automatically starts the appropriate device type
"""

import config

# Device configuration - SET THIS FOR EACH ESP32
# Change to config.DEVICE_RECEIVER for the servo ESP32
DEVICE_TYPE = config.DEVICE_RECEIVER

def main():
    """Main boot function"""
    print("="*50)
    print("ESP32 SmartMotor System Starting")
    print("Device Type: {}".format(DEVICE_TYPE))
    print("="*50)
    
    try:
        from smartmotor_main import SmartMotorController
        controller = SmartMotorController(DEVICE_TYPE)
        controller.run()
        
    except ImportError as e:
        print("Import error: {}".format(e))
        print("Make sure all required files are uploaded to the ESP32")
        
    except KeyboardInterrupt:
        print("Boot interrupted by user")
        
    except Exception as e:
        print("Boot error: {}".format(e))
        import sys
        sys.print_exception(e)

if __name__ == "__main__":
    main()
