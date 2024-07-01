'''
Created on 14.03.2016

@author: kraft-p
'''

import asyncio
import json
import time
import inspect
import traceback
from attrdictionary import AttrDict
from . import Device, DeviceError


class BadRequest(Exception):
    def __init__(self, request, message):
        self.request = request
        self.message = message

class ServerError(Exception):
    def __init__(self, e, tb):
        self.exception = e
        self.traceback = tb

    def __repr__(self):
        return 'logger.ServerError({})'.format(repr(self.exception))


class JsonServer:
    """
    Handles JSON requests in the form
       - [cmd, data], where cmd is a string and data any json encoded data
       - cmd == '?': Returns the result from a getdata method or coroutine or the property data
                  If none is present, an error is raised
       - cmd == '??': Returns a dictionary of all available commands and their docstrings
       - cmd == 'do_*': Tries to call a method or coroutine do_xy(**kwargs)

    How to subclass:
    In most cases, you need just to implement a getdata method / coroutine and for any
    behaviour a do_xxx method / coroutine. The TestJsonServer implementation below shows it for a simple cas.
    When you need a new __init__ method, do not forget to call super().__init__ as a first line
    """
    
    def __init__(self, port, serve_all=False):
        """
        Initializes the server, but does not open it
        Use JsonServer.create to create an open server
        :param port: port to serve
        :param serve_all: If True, serve to all hosts, else only localhost
        """
        self.closed = asyncio.Event()
        self.verbose = False
        self.lock = asyncio.Lock()
        self.server = None
        self.port = port
        self.host = None if serve_all else '127.0.0.1'

    @classmethod
    async def create(cls, port, serve_all=False):
        """
        Creates and opens the server
        :param port: port to serve
        :param serve_all: If True, serve to all hosts, else only localhost
       :return: The server
        """
        server_obj = cls(port, serve_all)
        await server_obj.open()
        return server_obj

    def __repr__(self):
        return "{}(port={},open={})".format(type(self).__name__,self.port, not self.closed.is_set())

    async def open(self):
        """
        Opens the server
        """
        self.closed.clear()
        if self.server:
            raise RuntimeError('{} is already open'.format(self))
        self.server = await asyncio.start_server(self.handle_client, '127.0.0.1', self.port)
        if self.verbose:
            print('{} started on port {}'.format(self, self.port))

    async def close(self):
        """
        Closes the server, raises RuntimeError if server is closed already
        """
        if not self.server:
            raise RuntimeError('{} cannot be closed, never opened'.format(self))
        self.server.close()
        await self.server.wait_closed()
        if self.verbose:
            print('{} stopped listening on port {}'.format(self, self.port))
        self.closed.set()
        self.server = None

    async def handle_cmd(self, cmd, data):
        """
        Generic handler for commands.
        Usually not overridden.
        :param cmd:
        :param data:
        :return:
        """
        if cmd == '?':
            # Return dataa
            if hasattr(self, 'getdata'):
                resp = self.getdata()
                if asyncio.iscoroutine(resp):
                    return await resp
                else:
                    return resp
            elif hasattr(self, 'data'):
                return self.data
            else:
                raise BadRequest(cmd, '{}.? has no data provider (getdata method or data property)'.format(self))
        elif cmd == '??':
            # Return inspection
            resp = {'<class>': inspect.getdoc(self),
                    '?': 'Returns the data from the data property or getdata method',
                    }
            resp.update(dict((a, inspect.getdoc(getattr(self, a))) for a in dir(self) if a.startswith('do_')))
            return resp
        else:
            # Do command
            if hasattr(self, 'do_' + cmd):
                # get function from cmd name
                f = getattr(self, 'do_' + cmd)
                if not callable(f):
                    raise BadRequest(cmd, '{}.{}() is not callable'.format(self, 'do_' + cmd))
                try:
                    res = f(**(data or {}))
                except Exception as e:
                    raise ServerError(e, traceback.format_exc())
                if asyncio.iscoroutine(res):
                    return await res
                else:
                    return res
            else:
                raise BadRequest(cmd, '{}.{}() does not exist'.format(self, 'do_' + cmd))

    async def handle_client(self, reader, writer):
        """
        Handles a client request
        :param reader: Streamreader Object, connected with the client request
        :param writer: StreamWriter object, the response is written to
        :return:
        """
        try:
            request = await reader.readline()
            cmd, data = json.loads(request.decode())
            cmd = cmd.strip()
            addr = writer.get_extra_info('peername')
            if self.verbose:
                print("Received %r from %r" % (request.decode(), addr))
            if cmd == '!end':
                writer.write('{"ready":true}'.encode())

                await writer.drain()
                if self.verbose:
                    print("Attempt to close server")
                await self.close()
            else:
                try:
                    responsedata = await self.handle_cmd(cmd, data)
                except BadRequest as e:
                    responsedata = {'error': e.message, 'request': e.request}
                except ServerError as e:
                    responsedata = {'error': 'Server error in {}: {}'.format(type(self).__name__, repr(e.exception)),
                                    'traceback': e.traceback,
                                    'request': cmd}

                response = json.dumps(responsedata) + '\n'
                if self.verbose:
                    print('Response:', response)
                writer.write(response.encode())
                await writer.drain()
        finally:
            if self.verbose:
                print("Close the client socket")
            writer.close()


class TestJsonServer(JsonServer):
    """
    A test implementation with function and coroutine as command target
    """
    def getdata(self, **kwargs):
        kwargs.update({'test': 42, 'test2': 'bla', 'test3': None})
        return kwargs

    def do_noargs(self):
        return None


    def do_sync(self, **kwargs):
        """
        Returns the input data with some additional stuff
        """
        kwargs.update({'sync': 1, 'async': 0})
        return kwargs

    async def do_async(self, **kwargs):
        """
        Waits for 0.5 s and then returns the input data with some additional stuff
        """
        await asyncio.sleep(0.5)
        kwargs.update({'sync': 0, 'async': 1})
        return kwargs


class JsonClient(Device):
    """
    A simple client for a server implemented as a JSON server. For some servers an object of this class
    is sufficient, for more complex devices inherit from this
    """

    def __init__(self, host, port, name=None):
        self.host = host
        self.port = port
        self.name = name
        super().__init__()
        self.lock = asyncio.Lock()

    def __str__(self):
        return 'json://{}:{}'.format(self.name or self.host, self.port)
        
    async def send(self, cmd, **data):
        async with self.lock:
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
            except ConnectionRefusedError:
                self.active = False
                raise DeviceError('Connection refused by {}, deactivate'.format(self), self)
            data = json.dumps([cmd, data])
            writer.write(data.encode())
            writer.write_eof()
            response = await reader.readline()
            writer.close()
            return json.loads(response.decode(), object_pairs_hook=AttrDict)

    async def readstatus(self):
        response = await asyncio.wait_for(self.send('?'), timeout=0.3)
        self.data = response
        self.readtime = time.time()
        if self.data.get('ready') and self.is_ready:
            self.is_ready.set()
        return self

    async def stopserver(self):
        data = json.dumps(['!end', None]) + '\n'
        _reader, writer = await asyncio.open_connection(self.host, self.port)
        writer.write(data.encode())
        writer.close()
