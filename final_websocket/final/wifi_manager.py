"""
WiFi connection manager for ESP32 devices
Handles connection, reconnection, and status monitoring
"""

import network
import time
import config

class WiFiManager:
    def __init__(self, hardware_manager=None):
        """Initialize WiFi manager with optional hardware manager for display updates"""
        self.hardware_manager = hardware_manager
        self.wlan = None
        self.connected = False
        self.ip_address = None
        
    def connect(self):
        """Connect to WiFi network with timeout and status updates"""
        print(f"Connecting to WiFi: {config.WIFI_SSID}")
        
        if self.hardware_manager:
            self.hardware_manager.update_display("SmartMotor", "WiFi", "Connecting...", "")
        
        try:
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(True)
            
            # If already connected, check if it's the same network
            if self.wlan.isconnected():
                self.ip_address = self.wlan.ifconfig()[0]
                self.connected = True
                print(f"Already connected to WiFi. IP: {self.ip_address}")
                self._update_success_display()
                return True
            
            # Connect to network
            self.wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
            
            # Wait for connection with timeout
            timeout_counter = 0
            while not self.wlan.isconnected() and timeout_counter < config.WIFI_TIMEOUT:
                print(".", end="")
                time.sleep(1)
                timeout_counter += 1
                
                # Update display every 5 seconds
                if timeout_counter % 5 == 0 and self.hardware_manager:
                    self.hardware_manager.update_display(
                        "SmartMotor", "WiFi", f"Connecting {timeout_counter}s", ""
                    )
            
            print()  # New line after dots
            
            if self.wlan.isconnected():
                self.ip_address = self.wlan.ifconfig()[0]
                self.connected = True
                print(f"WiFi connected successfully! IP: {self.ip_address}")
                self._update_success_display()
                return True
            else:
                print("WiFi connection timeout")
                self._update_failure_display("Timeout")
                return False
                
        except Exception as e:
            error_msg = str(e)[:10]
            print(f"WiFi connection error: {e}")
            self._update_failure_display(error_msg)
            return False
    
    def _update_success_display(self):
        """Update display with successful connection"""
        if self.hardware_manager:
            ip_short = self.ip_address[:15] if len(self.ip_address) > 15 else self.ip_address
            self.hardware_manager.update_display("SmartMotor", "WiFi Connected", ip_short, "")
            time.sleep(2)  # Show success message briefly
    
    def _update_failure_display(self, error_type):
        """Update display with connection failure"""
        if self.hardware_manager:
            self.hardware_manager.update_display("SmartMotor", "WiFi Failed", error_type, "Check config")
    
    def is_connected(self):
        """Check if WiFi is still connected"""
        if not self.wlan:
            return False
            
        try:
            self.connected = self.wlan.isconnected()
            return self.connected
        except:
            return False
    
    def get_ip_address(self):
        """Get current IP address"""
        return self.ip_address
    
    def disconnect(self):
        """Disconnect from WiFi"""
        if self.wlan:
            try:
                self.wlan.disconnect()
                self.wlan.active(False)
            except:
                pass
        self.connected = False
        self.ip_address = None
        print("WiFi disconnected")
