# Configuration file for ESP32 SmartMotor system
# Contains ALL variables that are actually used in the code

# WiFi Configuration
WIFI_SSID = "tufts_eecs"
WIFI_PASSWORD = ""
WIFI_TIMEOUT = 20

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

# Communication Timing (your customized values)
SEND_INTERVAL_MS = 200
HEARTBEAT_INTERVAL_MS = 5000
MESSAGE_TIMEOUT_MS = 15000
MAX_RECONNECT_ATTEMPTS = 3
RECONNECTION_DELAY_S = 2

# Rate Limiting (your customized values)
MAX_MESSAGES_PER_WINDOW = 20
MESSAGE_WINDOW_MS = 5000

# Message Configuration
MAX_MESSAGE_SIZE = 100
RECEIVE_CHUNK_SIZE = 100
ANGLE_CHANGE_THRESHOLD = 2

# State Synchronization (your customized values)
STATE_SYNC_DELAY_MS = 1000
PARTNER_TIMEOUT_MS = 5000

# Device Types
DEVICE_CONTROLLER = "controller"
DEVICE_RECEIVER = "receiver"

