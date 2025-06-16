# ESP32 SmartMotor System - Optimized Version

## Overview
This is an optimized version of the ESP32 SmartMotor system that provides stable WebSocket communication between multiple ESP32 devices. The system has been restructured into modular components for better maintainability and significantly improved connection stability.

## Key Optimizations

### 1. Connection Stability Improvements
- **Reduced message frequency**: Decreased from constant sending to 500ms intervals
- **Improved buffer management**: Smaller, more efficient buffers (256 bytes vs 512 bytes)
- **Better error handling**: Graceful recovery from connection failures
- **Optimized WebSocket framing**: More efficient message creation and parsing
- **Memory leak prevention**: Regular garbage collection and proper resource cleanup

### 2. Code Structure Improvements
- **Modular design**: Split into 7 focused files (< 250 lines each)
- **Separation of concerns**: Each module handles a specific functionality
- **Improved error handling**: Better exception management throughout
- **Configuration management**: Centralized configuration in `config.py`

### 3. Performance Optimizations
- **Rate limiting**: Prevents message flooding
- **Dead zone filtering**: Reduces noise in potentiometer readings
- **Threaded architecture**: Separate sender/receiver threads when available
- **Single-threaded fallback**: Robust operation even without threading support

## File Structure

```
├── config.py              # Configuration constants
├── hardware_manager.py    # Hardware abstraction layer
├── wifi_manager.py        # WiFi connection management
├── websocket_manager.py   # WebSocket communication
├── message_handler.py     # Message processing and CEEO protocol
├── smartmotor_main.py     # Main controller coordination
└── boot.py               # Boot script for easy deployment
```

## Installation

1. **Upload all files** to your ESP32 devices using your preferred method (Thonny, ampy, etc.)

2. **Keep existing libraries**: The system still uses your existing libraries:
   - `icons.py` (for OLED display)
   - `servo.py` (for servo control)
   - `adxl345.py` (for accelerometer)
   - `sensors.py` (for sensor management)

3. **Configure device type** in `boot.py`:
   ```python
   # FOR CONTROLLER ESP32 (with potentiometer)
   DEVICE_TYPE = config.DEVICE_CONTROLLER
   
   # FOR RECEIVER ESP32 (with servo)
   DEVICE_TYPE = config.DEVICE_RECEIVER
   ```

4. **Update WiFi credentials** in `config.py` if needed:
   ```python
   WIFI_SSID = "your_network_name"
   WIFI_PASSWORD = "your_password"
   ```

## Usage

### Automatic Start
The system will automatically start when the ESP32 boots if you rename `boot.py` to `main.py` or call it from your existing `main.py`.

### Manual Start
Run `boot.py` from the REPL:
```python
exec(open('boot.py').read())
```

### Configuration Options
Edit `config.py` to adjust:
- **Send intervals**: How often data is transmitted
- **Timeouts**: Connection timeout values
- **Buffer sizes**: Memory allocation for messages
- **Hardware pins**: Pin assignments for components

## Monitoring

The system provides detailed console output showing:
- Connection status
- Message sequence numbers
- Error conditions
- Reconnection attempts

The OLED display shows:
- Device type and status
- Current angle values
- Sequence numbers
- Connection state

## Troubleshooting

### Connection Issues
- **"WebSocket connection failed"**: Check WiFi and server availability
- **"Connection timeout detected"**: Increase `MESSAGE_TIMEOUT_MS` in config
- **"Max reconnection attempts reached"**: Check network stability

### Hardware Issues
- **"Potentiometer initialization failed"**: Check pin 3 connection
- **"Servo initialization failed"**: Check pin 2 connection and power
- **"Display initialization failed"**: Check I2C connections (pins 6, 7)

### Performance Issues
- **Messages too frequent**: Increase `SEND_INTERVAL_MS` in config
- **Memory errors**: Decrease `MAX_BUFFER_SIZE` in config
- **Slow response**: Decrease `ANGLE_CHANGE_THRESHOLD` in config

## Key Differences from Original

### Stability Improvements
- **Connection monitoring**: Active health checking with automatic recovery
- **Rate limiting**: Prevents overwhelming the WebSocket connection
- **Buffer management**: Efficient memory usage prevents crashes
- **Error recovery**: Graceful handling of network issues

### Architecture Changes
- **Modular design**: Each component has a single responsibility
- **Centralized configuration**: Easy to modify behavior
- **Improved threading**: Better coordination between sender/receiver
- **Resource management**: Proper cleanup prevents memory leaks

### Message Flow
1. **Controller**: Reads potentiometer → Filters changes → Sends when significant
2. **Receiver**: Receives angle → Moves servo → Sends status back
3. **Heartbeat**: Both devices send periodic heartbeats to maintain connection
4. **Recovery**: Automatic reconnection when connection fails

## Expected Behavior

With these optimizations, you should see:
- **Stable connections** lasting hours instead of minutes
- **Consistent message delivery** without dropped connections
- **Automatic recovery** from temporary network issues
- **Smooth servo movement** without jitter
- **Clear status feedback** on both console and display

The system is now much more robust and suitable for extended demonstrations or deployments.
