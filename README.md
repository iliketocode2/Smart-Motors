# ESP32 Wireless and Pyscript-page-less solutions

## Websockets Only
This implementation, found in final_websocket/final, involves handling the entire websocket connection on the esp32s.
- Pros:
   - All code self-contained, nothing relies on external sites or systems
- Cons:
   - Unreliable connection that is occasionally interrupted when the Smart Motor disconnects from the websocket
   - Slow connection time: ~1.6s
## HTTP Bruidge
Using JSONbin.io and HTTP POST requests, the esp32s send data to the JSON cloud bin and retreive messages from there as well
-  Pros:
   - Very reliable connection. Only limited by the JSONbin API limits
- Cons:
   - Slow connection: ~1.9s

## Pyscript Page Connection
The pyscript_page folder contains an incomplete implementation that attempts to use a single pyscript page to setup and connect the Smart Motors over channels

### Test Programs
This folder contains programs that test the various parts of the smart motor for functionality. They also provide good examples of usage of the servo, OLED screen, potentiometer, buttons, etc.
