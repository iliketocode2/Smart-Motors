import asyncio
import json

async def myCallback(message):
    value = json.loads(message.decode())

def fred(message):
    payload = message['payload']
    payload_dict = json.loads(payload)
    topic = payload_dict['topic']
    value = payload_dict['value']
    if (topic == "/controller/data"):
        await x.right_angle(angle = value)
    
myChannel.callback = fred
