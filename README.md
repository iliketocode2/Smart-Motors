# ESP32 Wireless and Pyscript-page-less solutions

## Instructions
Since the Direct TCP Communication is the fastest and most reliable of all of the solutions I have come up with, here are the instructions on how to setup this communication on your ESP32 Smart Motors:
1. Navigate to the [direct_TCP folder](https://github.com/iliketocode2/Smart-Motors/tree/main/direct_TCP)
2. Update the wifi information in receiver.py
3. Run the receiver.py program on your receiver esp32
4. Once it connects to the internet, look for and copy its IP address in your IDE console.
5. Update wifi information in controller.py and update controller.py with the receiver's IP
6. Run the controller.py program on your controller esp32

## Overview of the communication systems
### Direct TCP Communication
MicroPython's network library (WLAN class) combined with the socket module has full capacity to create two-way TCP protocol.
- Pros:
   - Local Network Control: No internet outages affect communication, router manages all traffic - optimized paths
   - TCP Reliability: Automatic retransmission of lost packets, connection state tracking - knows when connection breaks
   - Simple Protocol: Fewer failure points - just WiFi + TCP + JSON (which makes for easier debugging!)
- Cons:
   - Slightly slow connection ~0.25s (can be mitigated with delay changes throughout however)
### Websockets Only
This implementation, found in final_websocket/final, involves handling the entire websocket connection on the esp32s.
- Pros:
   - All code self-contained, nothing relies on external sites or systems
- Cons:
   - Unreliable connection that is occasionally interrupted when the Smart Motor disconnects from the websocket
   - Slow connection time: ~1.6s
### HTTP Bridge
Using JSONbin.io and HTTP POST requests, the esp32s send data to the JSON cloud bin and retreive messages from there as well
-  Pros:
   - Very reliable connection. Only limited by the JSONbin API limits
- Cons:
   - Slow connection: ~1.9s

### Pyscript Page Connection
The pyscript_page folder contains an incomplete implementation that attempts to use a single pyscript page to setup and connect the Smart Motors over channels

#### Test Programs
This folder contains programs that test the various parts of the smart motor for functionality. They also provide good examples of usage of the servo, OLED screen, potentiometer, buttons, etc.
