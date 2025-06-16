# Configuration file for ESP32 SmartMotor system

# WiFi Configuration
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""
WIFI_TIMEOUT = 30

# WebSocket Configuration
WS_HOST = "chrisrogers.pyscriptapps.com"
WS_PORT = 443
WS_PATH = "/talking-on-a-channel/api/channels/hackathon"

# Hardware Configuration
SERVO_PIN = 2
POTENTIOMETER_PIN = 3
DISPLAY_SCL_PIN = 7
DISPLAY_SDA_PIN = 6
DISPLAY_RST_PIN = 10

# Communication Configuration
SEND_INTERVAL_MS = 500  # Reduced frequency for stability
HEARTBEAT_INTERVAL_MS = 10000  # Less frequent heartbeats
MESSAGE_TIMEOUT_MS = 45000  # Longer timeout before declaring connection dead
MAX_RECONNECT_ATTEMPTS = 3
RECONNECTION_DELAY_S = 5

# Buffer Configuration
MAX_BUFFER_SIZE = 256  # Smaller buffer to prevent memory issues
RECEIVE_CHUNK_SIZE = 128
POTENTIOMETER_DEAD_ZONE = 5  # Larger dead zone to reduce noise

# Message Configuration
MAX_MESSAGE_SIZE = 400
ANGLE_CHANGE_THRESHOLD = 3  # Minimum angle change to trigger send

# Device Types
DEVICE_CONTROLLER = "controller"
DEVICE_RECEIVER = "receiver"
