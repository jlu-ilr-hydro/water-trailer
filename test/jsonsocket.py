#!/usr/bin/python3
"""
Checks the JsonClient / Server pair in trailer.devices.jsonclient
"""
import sys
import asyncio
import yaml


from trailer.devices.jsonclient import JsonClient, TestJsonServer


async def clienttest(client: JsonClient, cmd=None, yaml_file=None):
    if not cmd:
        print('?')
        await client.readstatus()
        print(yaml.dump(client.data, default_flow_style=False))
        print('-' * 50)

        print('??')
        data = await client.send('??')
        print(yaml.dump(data, default_flow_style=False))
        print('-' * 50)
    else:
        print(cmd)
        if yaml_file:
            data_in = yaml.load(open(yaml_file))
        else:
            data_in = {}
        data = await client.send(cmd, **data_in)
        print(yaml.dump(data, default_flow_style=False))


async def loadtest(client: JsonClient):

    loop = asyncio.get_event_loop()
    connect_count = 1000
    for i in range(1000):
        tstart = loop.time()
        for j in range(connect_count):
            await client.readstatus()
        tend = loop.time()
        print('#{:10,}: {:0.2f}ms/call sampling {} calls'.format(i * connect_count, (tend-tstart)/connect_count * 1000, connect_count))





if __name__ == '__main__':
    import sys
    loop = asyncio.get_event_loop()
    # loop.set_debug(1)
    if 'server' in sys.argv:
        jserver = TestJsonServer(51213)
        jserver.verbose = True
        loop.run_until_complete(jserver.open())
        try:
            loop.run_until_complete(jserver.closed.wait())
        except KeyboardInterrupt:
            pass
    elif 'heavy' in sys.argv:
        client = JsonClient('127.0.0.1', 51213)
        loop.run_until_complete(loadtest(client))

    else:
        client = JsonClient('127.0.0.1', 51213)
        if 'stop' in sys.argv:
            loop.run_until_complete(client.stopserver())
        else:
            loop.run_until_complete(clienttest(client, *sys.argv[1:]))
