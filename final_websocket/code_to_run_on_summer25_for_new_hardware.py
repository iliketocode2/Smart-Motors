import asyncio
import json

async def myCallback(message):
    value = json.loads(message.decode())

def fred(message):    
    await x.motor_speed(1, 50)
    payload = message['payload']
    payload_dict = json.loads(payload)
    topic = payload_dict['topic']
    value = payload_dict['value']
    
    if (topic == "/controller/data") and (value != "heartbeat"):
        final_pos = int((value / 180) * 270)
        print("Final Pos: ", final_pos)
        await x.right_abs_pos(final_pos)
    
myChannel.callback = fred
