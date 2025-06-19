#!/usr/bin/env python3
"""
SmartMotor HTTP Bridge Server
Bridges ESP32 HTTP requests to CEEO WebSocket channels

Run with: python3 bridge_server.py
"""

import asyncio
import websockets
import json
import time
import logging
import threading
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import signal
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bridge.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
CEEO_WS_URL = "wss://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon"
BRIDGE_HOST = "0.0.0.0"  # Listen on all interfaces
BRIDGE_PORT = 8080
WEBSOCKET_RECONNECT_DELAY = 5  # seconds
MAX_RECONNECT_ATTEMPTS = 10

class SmartMotorBridge:
    def __init__(self):
        self.devices = {
            'controller': {
                'angle': 90,
                'last_update': time.time(),
                'update_count': 0
            },
            'receiver': {
                'angle': 90,
                'last_update': time.time(),
                'update_count': 0
            }
        }
        self.websocket = None
        self.websocket_connected = False
        self.websocket_reconnect_attempts = 0
        self.running = True
        
        # Statistics
        self.stats = {
            'bridge_start_time': time.time(),
            'total_http_requests': 0,
            'total_websocket_messages': 0,
            'last_error': None
        }
        
        logger.info("SmartMotor Bridge initialized")
    
    async def websocket_handler(self):
        """Handle WebSocket connection to CEEO channels with auto-reconnect"""
        while self.running:
            try:
                logger.info(f"Connecting to CEEO WebSocket: {CEEO_WS_URL}")
                
                async with websockets.connect(
                    CEEO_WS_URL,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10
                ) as websocket:
                    self.websocket = websocket
                    self.websocket_connected = True
                    self.websocket_reconnect_attempts = 0
                    logger.info("CEEO WebSocket connected successfully")
                    
                    # Listen for messages
                    async for message in websocket:
                        try:
                            await self.handle_websocket_message(message)
                        except Exception as e:
                            logger.error(f"Error handling WebSocket message: {e}")
                            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("CEEO WebSocket connection closed")
            except Exception as e:
                logger.error(f"CEEO WebSocket error: {e}")
                self.stats['last_error'] = str(e)
            
            # Connection lost
            self.websocket_connected = False
            self.websocket = None
            
            if not self.running:
                break
                
            # Reconnect logic
            self.websocket_reconnect_attempts += 1
            if self.websocket_reconnect_attempts <= MAX_RECONNECT_ATTEMPTS:
                logger.info(f"Reconnecting in {WEBSOCKET_RECONNECT_DELAY}s (attempt {self.websocket_reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS})")
                await asyncio.sleep(WEBSOCKET_RECONNECT_DELAY)
            else:
                logger.error("Max WebSocket reconnect attempts reached")
                break
    
    async def handle_websocket_message(self, message):
        """Process incoming WebSocket messages from CEEO channel"""
        try:
            data = json.loads(message)
            self.stats['total_websocket_messages'] += 1
            
            # Handle welcome message
            if data.get('type') == 'welcome':
                logger.info("CEEO Channel welcomed - connection established")
                return
            
            # Handle data messages
            if data.get('type') == 'data' and 'payload' in data:
                payload = json.loads(data['payload'])
                topic = payload.get('topic', '')
                value = payload.get('value')
                
                logger.debug(f"CEEO message: {topic} = {value}")
                
                # Update device state based on topic
                if topic == '/controller/data' and isinstance(value, (int, float)):
                    self.devices['receiver']['angle'] = int(value)
                    self.devices['receiver']['last_update'] = time.time()
                    logger.info(f"Updated receiver target: {value}°")
                elif topic == '/receiver/data' and isinstance(value, (int, float)):
                    self.devices['controller']['angle'] = int(value)
                    self.devices['controller']['last_update'] = time.time()
                    logger.info(f"Received confirmation: {value}°")
                    
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
    
    async def send_to_ceeo_channel(self, topic, value):
        """Send data to CEEO channel via WebSocket"""
        if not self.websocket_connected or not self.websocket:
            logger.warning(f"Cannot send to CEEO channel - not connected")
            return False
        
        try:
            payload = {
                'topic': topic,
                'value': value
            }
            message = json.dumps(payload)
            await self.websocket.send(message)
            logger.debug(f"Sent to CEEO: {topic} = {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to send to CEEO channel: {e}")
            return False
    
    def update_device_data(self, device_id, angle):
        """Update device data and forward to CEEO channel"""
        if device_id not in self.devices:
            logger.warning(f"Unknown device: {device_id}")
            return False
        
        # Update local state
        self.devices[device_id]['angle'] = angle
        self.devices[device_id]['last_update'] = time.time()
        self.devices[device_id]['update_count'] += 1
        
        # Forward to CEEO channel
        topic = f"/{device_id}/data"
        asyncio.create_task(self.send_to_ceeo_channel(topic, angle))
        
        logger.info(f"Device {device_id} updated: {angle}° (total updates: {self.devices[device_id]['update_count']})")
        return True
    
    def get_device_data(self, device_id):
        """Get current data for a device"""
        if device_id not in self.devices:
            logger.warning(f"Unknown device requested: {device_id}")
            return None
        
        return self.devices[device_id].copy()
    
    def get_status(self):
        """Get bridge status for monitoring"""
        uptime = time.time() - self.stats['bridge_start_time']
        return {
            'uptime_seconds': uptime,
            'websocket_connected': self.websocket_connected,
            'websocket_reconnect_attempts': self.websocket_reconnect_attempts,
            'devices': self.devices,
            'stats': self.stats,
            'timestamp': datetime.now().isoformat()
        }
    
    def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down SmartMotor Bridge")
        self.running = False

# Global bridge instance
bridge = SmartMotorBridge()

# Flask app for HTTP endpoints
app = Flask(__name__)

@app.route('/')
def status_page():
    """Web status page for monitoring"""
    status = bridge.get_status()
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>SmartMotor Bridge Status</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .status { margin: 10px 0; padding: 10px; border: 1px solid #ccc; }
            .connected { background-color: #d4edda; }
            .disconnected { background-color: #f8d7da; }
            .device { margin: 5px 0; padding: 5px; background-color: #f8f9fa; }
        </style>
    </head>
    <body>
        <h1>SmartMotor Bridge Status</h1>
        <div class="status {{ 'connected' if websocket_connected else 'disconnected' }}">
            <h3>WebSocket Status</h3>
            <p>Connected: {{ websocket_connected }}</p>
            <p>Reconnect Attempts: {{ websocket_reconnect_attempts }}</p>
        </div>
        
        <div class="status">
            <h3>Bridge Statistics</h3>
            <p>Uptime: {{ "%.1f"|format(uptime_seconds) }} seconds</p>
            <p>Total HTTP Requests: {{ stats.total_http_requests }}</p>
            <p>Total WebSocket Messages: {{ stats.total_websocket_messages }}</p>
            {% if stats.last_error %}
            <p>Last Error: {{ stats.last_error }}</p>
            {% endif %}
        </div>
        
        <div class="status">
            <h3>Device Status</h3>
            {% for device_id, device_data in devices.items() %}
            <div class="device">
                <strong>{{ device_id.title() }}:</strong>
                Angle: {{ device_data.angle }}°,
                Last Update: {{ "%.1f"|format(timestamp_now - device_data.last_update) }}s ago,
                Updates: {{ device_data.update_count }}
            </div>
            {% endfor %}
        </div>
        
        <p><em>Last Updated: {{ timestamp }}</em></p>
    </body>
    </html>
    """
    
    import time
    return render_template_string(html, 
                                timestamp_now=time.time(),
                                **status)

@app.route('/api/status')
def api_status():
    """JSON status endpoint"""
    return jsonify(bridge.get_status())

@app.route('/api/<device_id>', methods=['POST'])
def update_device(device_id):
    """HTTP endpoint for ESP32s to send data"""
    bridge.stats['total_http_requests'] += 1
    
    try:
        data = request.get_json()
        if not data or 'angle' not in data:
            return jsonify({'error': 'Missing angle data'}), 400
        
        angle = int(data['angle'])
        if not (0 <= angle <= 180):
            return jsonify({'error': 'Angle must be 0-180'}), 400
        
        success = bridge.update_device_data(device_id, angle)
        if success:
            return jsonify({'status': 'ok', 'angle': angle})
        else:
            return jsonify({'error': 'Failed to update device'}), 500
            
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid data from {device_id}: {e}")
        return jsonify({'error': 'Invalid data format'}), 400
    except Exception as e:
        logger.error(f"Error updating {device_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/<device_id>', methods=['GET'])
def get_device(device_id):
    """HTTP endpoint for ESP32s to get data"""
    bridge.stats['total_http_requests'] += 1
    
    try:
        # For receiver, get controller data (and vice versa)
        target_device = 'controller' if device_id == 'receiver' else 'receiver'
        data = bridge.get_device_data(target_device)
        
        if data:
            return jsonify({
                'angle': data['angle'],
                'last_update': data['last_update'],
                'age_seconds': time.time() - data['last_update']
            })
        else:
            return jsonify({'error': 'Device not found'}), 404
            
    except Exception as e:
        logger.error(f"Error getting data for {device_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Received shutdown signal")
    bridge.shutdown()
    sys.exit(0)

def start_bridge_server():
    """Start the HTTP bridge server"""
    logger.info(f"Starting SmartMotor Bridge Server on {BRIDGE_HOST}:{BRIDGE_PORT}")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start WebSocket handler in background thread
    def websocket_thread():
        asyncio.run(bridge.websocket_handler())
    
    ws_thread = threading.Thread(target=websocket_thread, daemon=True)
    ws_thread.start()
    
    # Start Flask app
    try:
        app.run(host=BRIDGE_HOST, port=BRIDGE_PORT, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}")
        bridge.shutdown()

if __name__ == '__main__':
    start_bridge_server()
