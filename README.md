# ESP32 Wireless and Pyscript-page-less solutions

- **Python Solutions:** contains code that successfully connects to the WebSockets using Python. While this cannot be run on an esp32, it was a test to see how easy it would be to write all of this connection code in a more robust language (Python rather than MicroPython).
- **ROS_Integrations:** was never actually implemented. That code can mostly just be ignored
- **Test Programs:** contains programs that run on the Smart Motors. Wrote these at the beginning of the summer to play around with using the Smart Motors. They also provide good examples of usage of the servo, OLED screen, potentiometer, buttons, etc.

- **direct_TCP:** esp32 to esp32 connection over direct TCP
- **final_websocket:** code to run on the new hardware which can be connected over websockets to the Smart Motors using one of Chris's Pyscript pages ([Summer25](https://pyscript.com/@chrisrogers/summer25/latest?files=README.md), [Summer25_Guts](https://pyscript.com/@chrisrogers/summer25-guts/latest?files=README.md))
   - **final:** has the latest/final version of the websocket code that would run on the Smart Motors. Run using smartmotor_main.py (or load boot.py onto an esp32)
- **http_bridge:** uses HTTP post to send data to and from Smart Motors. Used the online site JSONbin to collect requests. Also tested with requestbin. (NOTE: built in delay with HTTP requests as it's not meant to be a 2-way communication technology). Keep alive was meant to create a buffer that the receiving Smart Motor could constantly read from but this failed.
- **pyscript_page:** was meant to be a page that listened to actvity on the websocket. This folder contains an incomplete implementation that attempts to use a single pyscript page to setup and connect the Smart Motors over channels
- **talking_on_anyone:** contains the code for [Chris's Pyscript page by the same name](https://pyscript.com/@chrisrogers/talking-on-anyone/latest?files=README.md). Used this Pyscript page to do testing using the channel feature.


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
   - Slow connection time: ~0.8s
### HTTP Bridge
Using JSONbin.io and HTTP POST requests, the esp32s send data to the JSON cloud bin and retreive messages from there as well
-  Pros:
   - Very reliable connection. Only limited by the JSONbin API limits
- Cons:
   - Slow connection: ~1.9s
 
## Further Documentation:
Visit the Notion page [here](https://fetlab.notion.site/Smart-Motors-with-Websockets-23cdf3d0e05280e59db1ee467530549b?source=copy_link).
