import websocket
import ssl
import json

uri = "wss://chrisrogers.pyscriptapps.com/talking-on-a-channel/api/channels/hackathon"

class wss_CEEO():
    def __init__(self, url):
        self.url = url
    
    def send_message(self, message):
        """Send a single message and close connection"""
        ws = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_NONE})
        try:
            ws.connect(self.url)
            ws.send(json.dumps(message))
            print(f"Sent: {message}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            ws.close()
    
    def send_multiple(self, messages):
        """Send multiple messages using one connection"""
        ws = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_NONE})
        try:
            ws.connect(self.url)
            for message in messages:
                ws.send(json.dumps(message))
                print(f"Sent: {message}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            ws.close()

if __name__ == "__main__":
    client = wss_CEEO(uri)
    
    # Send a single message
    client.send_message({
        'topic': 'fred/image',
        'value': 9
    })
    
    # Or send multiple messages at once
    messages = [
        {'topic': 'test1', 'value': 'hello'},
        {'topic': 'test2', 'value': 'world'}
    ]
    client.send_multiple(messages)
