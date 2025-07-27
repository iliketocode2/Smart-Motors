import asyncio
import websockets
import ssl
import json

uri = "wss://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon"

class wss_CEEO():
    def __init__(self, url):
        self.url = url
        
    
async def send(websocket):
    counter = 1
    while True:
        try:
            message = { 'topic': 'heartbeat','value': counter }

            await websocket.send(json.dumps(message))

            counter += 1
            await asyncio.sleep(5)  # Send every 5 seconds
        except Exception as e:
            print(f"Error sending periodic message: {e}")
            break

async def listening(websocket):
    """Listen for incoming messages"""
    async for msg in websocket:
        try:
            message = json.loads(msg)
            if message['type'] == 'data' and message['payload']:
                try:
                    payload = json.loads(message['payload'])
                    if 'heartbeat' not in payload['topic']:
                        print(f'received {payload["value"]}')
                except json.JSONDecodeError:
                    pass
        except json.JSONDecodeError:
            print(f"Non-JSON message: {msg}")

async def client():
    try:
        async with websockets.connect(uri, ssl=True) as websocket:
            print("Connected successfully")

            message = { 'topic': 'fred/image','value': 9 }
            
            await websocket.send(json.dumps(message))
            print(f"Sent initial: {message}")
            
            # Run both tasks concurrently
            await asyncio.gather(
                send(websocket),
                listening(websocket)
            )
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(client())
