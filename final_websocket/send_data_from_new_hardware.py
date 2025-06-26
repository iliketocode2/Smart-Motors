import asyncio

print(y.reply)
async def light(message):
    value = message['leftAngle']
    mapped = int((value + 5000) / 100)
    if myChannel.connected:
        await myChannel.post('/URarm/test', mapped)


y.final_callback = light
