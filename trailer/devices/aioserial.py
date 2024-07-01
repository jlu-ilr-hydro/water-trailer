'''
Created on 18.03.2016

@author: Benjamin Dummer
https://gist.github.com/dummerbd/75316ab8c109b5bbc46b

Uses threading to use serial connection with asyncio
'''
import asyncio
import threading
import queue
import serial
import logging
import os

logger = logging.getLogger(__name__)


class LinesBuffer:
    """
    Simple buffer for splitting a byte string on new lines.
    """
    def __init__(self):
        self._buffer = bytearray()
        self._last_i = 0

    def add(self, data):
        """
        Add raw data bytes to the buffer.
        """
        self._buffer += data

    def next(self, maxlen):
        """
        Get the next line from the buffer or `maxlen` number of characters or
        None if `maxlen` number of characters are not available yet and a new
        line character hasn't been encountered yet. All newline characters are
        normalized to `\n`.
        """
        line = None
        i, c = 0, 0
        N, R = 13, 10

        # Pick up where we left off last
        for i in range(self._last_i, len(self._buffer)):
            c = self._buffer[i]
            if c == N or c == R:
                line = self._buffer[:i]
                break

        # Save where we left off
        self._last_i = i

        # Max characters read in with no newline
        if line is None and len(self._buffer) >= maxlen:
            line = self._buffer[:maxlen]
            self._buffer = self._buffer[maxlen:]

            self._last_i = 0

            # No newline
            return line

        # No new-lines read
        if line is None:
            return None

        # Consume new line character
        i += 1
        # Consume paired new line character if present
        p = self._buffer[i] if i < len(self._buffer) else None
        if p is not None and c != p and (p == N or p == R):
            i += 1

        # Trim buffer
        self._buffer = self._buffer[i:]

        self._last_i = 0

        # Return line with a \n on the end
        return line + b'\n'

    def clear(self):
        """
        Clear the bufffer.
        """
        self._buffer = bytearray()


class SerialTransport(asyncio.Transport):
    """
    Threaded serial transport.
    """
    write_buffer_size = 16
    write_buffer_low = 4
    write_buffer_high = 10

    def __init__(self, loop, serial_factory, protocol):
        self._loop = loop
        self._protocol = protocol

        self._is_closing = False
        self._pause_reading = False
        self._extra_info = {}

        self._out = queue.Queue(self.write_buffer_size)
        self._out_high = self.write_buffer_high
        self._out_low = self.write_buffer_low
        self._out_paused = False
        self._out_lock = threading.Lock()

        self._worker_thread = threading.Thread(
            target=self._worker, name='SerialTransport.worker', daemon=True, args=(serial_factory,))
        self._worker_thread.start()

        self._loop.call_soon(self._protocol.connection_made, self)

    def _worker(self, serial_factory):
        """
        Worker thread that handles the blocking calls of the serial port.
        """
        ser = serial_factory()
        ser.timeout = 1.0
        ser.writeTimeout = 1.0
        buf = bytearray()

        # Record some extra info about the serial port
        self._extra_info = {k: getattr(ser, k, None) for k in [
            'name', 'port', 'baudrate', 'bytesize', 'parity', 'stopbits'
        ]}

        try:
            while not self._is_closing and ser.isOpen():
                # Get output data to write
                try:
                    data = self._out.get_nowait()
                except queue.Empty:
                    pass
                else:
                    self._out.task_done()
                    ser.write(data)

                # Resume writing if needed
                self._maybe_resume_protocol(threadsafe=True)

                # Read in any incoming data
                if ser.inWaiting() > 0:
                    data = ser.read(ser.inWaiting())
                    buf += data

                # Only call data_received when not paused
                if not self._pause_reading and len(buf) > 0:
                    self._loop.call_soon_threadsafe(self._protocol.data_received, buf)
                    buf.clear()

        except Exception as exc:
            self._close(exc)

        finally:
            if ser and ser.isOpen():
                ser.close()
            self._extra_info = {}

    def _maybe_pause_protocol(self, threadsafe=False):
        """
        This is a modified version of the ascio.protocol._FlowControlMixin
        method of the same name.
        It is called when the input buffer increases in size.
        """
        with self._out_lock:
            size = self.get_write_buffer_size()
            if size <= self._out_high:
                return
            if not self._out_paused:
                self._out_paused = True
                try:
                    if threadsafe:
                        self._loop.call_soon_threadsafe(self._protocol.pause_writing)
                    else:
                        self._protocol.pause_writing()
                except Exception as exc:
                    self._loop.call_exception_handler({
                        'message': 'protocol.pause_writing() failed',
                        'exception': exc,
                        'transport': self,
                        'protocol': self._protocol,
                    })

    def _maybe_resume_protocol(self, threadsafe=False):
        """
        This is a modified version of the ascio.protocol._FlowControlMixin
        method of the same name.
        It is called when the input buffer decreases in size.
        """
        with self._out_lock:
            if self._out_paused and self.get_write_buffer_size() <= self._out_low:
                self._out_paused = False

                try:
                    if threadsafe:
                        self._loop.call_soon_threadsafe(self._protocol.resume_writing)
                    else:
                        self._protocol.resume_writing()
                except Exception as exc:
                    self._loop.call_exception_handler({
                        'message': 'protocol.resume_writing() failed',
                        'exception': exc,
                        'transport': self,
                        'protocol': self._protocol,
                    })

    def _close(self, exc):
        """
        Serial port closed after exception.
        """
        self._loop.call_soon_threadsafe(self._protocol.connection_lost, exc)

    def close(self):
        """
        Close the serial port.
        """
        self._is_closing = True
        self._worker_thread.join()
        self._close(None)

    def is_closing(self):
        """
        Is the serial port closed/closing?
        """
        return self._is_closing

    def get_extra_info(self, name, default=None):
        """
        Provide extra info about the serial port.
        """
        return self._extra_info.get(name, default)

    def pause_reading(self):
        """
        Pause reading until resume_reading is called.
        """
        self._pause_reading = True

    def resume_reading(self):
        """
        Resume reading if it was paused.
        """
        self._pause_reading = False

    def abort(self):
        """
        Abort write operations.
        """
        self.close()

    def write(self, data):
        """
        Write data to the serial port.
        """
        success = True
        try:
            self._out.put_nowait(data)
        except queue.Full:
            success = False

        self._maybe_pause_protocol()

        return success

    def writelines(self, data_list):
        """
        Write multiple lines to the serial port.
        """
        for data in data_list:
            self.write(data)

    def get_write_buffer_size(self):
        """
        Get the size of the write buffer.
        """
        return self._out.qsize()

    def get_write_buffer_limits(self):
        """
        Get the high and low water marks for the write buffer.
        """
        return (self._out_low, self._out_high)

    def set_write_buffer_limits(self, high=None, low=None):
        """
        Set the high and low water marks for the write buffer.
        """
        self._out_high = high if high is not None else self.write_buffer_high
        if self._out_high == 0:
            self._out_low = 0
        elif low is None:
            self._out_low = self._out_high // 2
        else:
            self._out_low = min(self._out_high, low)
        self._maybe_pause_protocol()

    def can_write_eof(self):
        """
        EOF not supported.
        """
        return False

    def write_eof(self):
        """
        Not supported.
        """
        raise NotImplementedError



async def create_connection(protocol_factory, loop=None, **serial_kwargs):
    """
    Create a serial streaming transport connection to a serial port.
    """
    if loop is None:
        loop = asyncio.get_event_loop()

    def serial_factory():
        return serial.Serial(**serial_kwargs)

    protocol = protocol_factory()
    return SerialTransport(loop, serial_factory, protocol), protocol


async def open_serial_connection(threaded=False, limit=1024, loop=None, **serial_kwargs):
    """
    Get a stream reader and a stream writer for a serial connection.
    """
    if loop is None:
        loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader(limit=limit, loop=loop)
    protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
    if threaded:
        transport, _ = await create_connection(lambda: protocol, loop=loop, **serial_kwargs)
    else:
        import serial.aio as aio
        transport, _ = await aio.create_serial_connection(loop, lambda: protocol, **serial_kwargs)
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)
    return reader, writer


class Ser2Net:
    """
    Wraps a serial port bound to a tcp port using ser2net

    Usage:
    serial = Ser2Net('/dev/ttyUSB4', timeout=1.0)
    await serial.write(b'2I!')
    resp = await serial.readline()
    """
    def __init__(self, device, host='127.0.0.1', **serial_kwargs):
        self.devices = {}
        self.host = host
        self.device = device
        if os.path.exists('/etc/ser2net.conf'):
            with open('/etc/ser2net.conf') as f:
                for line in f:
                    if not line.strip().startswith('#') and line.strip():
                        parts = line.split(':', maxsplit=4)
                        if len(parts) < 5 or parts[0].upper().strip() == 'BANNER':
                            continue
                        else:
                            tcpport, proto, timeout, device, config = parts
                            self.devices[device] = (int(tcpport), proto, timeout, config)
        self.reader = None
        self.serial_kwargs = serial_kwargs
        self.timeout = serial_kwargs.get('timeout', 1.0)
        self.writer = None
    def close(self):
        if self.writer:
            self.writer.close()
    async def open(self):
        """
        Opens a tcp connection using ser2net if available, else uses serial.aio.create_connection
        :param device:
        :return:
        """
        if self.device in self.devices:
            tcpport = self.devices[self.device][0]
            self.reader, self.writer = await asyncio.open_connection(host=self.host, port=tcpport)
        else:
            self.reader, self.writer = await open_serial_connection(port=self.device, **self.serial_kwargs)

    async def write(self, byte_msg: bytes):
        """
        Writes a byte message to the serial port over ser2net
        :param byte_msg: bytestring message
        :return: None
        """
        if not self.writer:
            await self.open()

        self.writer.write(byte_msg)
        await self.writer.drain()

    def write_fast(self, byte_msg: bytes):
        """
        Writes a byte message to the serial port over ser2net
        :param byte_msg: bytestring message
        :return: None
        """
        self.writer.write(byte_msg)

    async def read(self, n):
        """
        Reads n bytes from the ser2net port
        Stops with timeout
        :param n: number of bytes to read
        :return: bytestring message, empty string on timeout
        """
        if not self.reader:
            await self.open()
        try:
            msg = await asyncio.wait_for(self.reader.read(n), timeout=self.timeout)
        except asyncio.TimeoutError:
            msg = b''

        return msg

    async def readexactly(self, n):
        """
        Like read but raises an error if less than n bytes come back.
        Stops with timeout
        :param n: number of bytes to read
        :return: bytestring message
        """
        if not self.reader:
            await self.open()
        try:
            return await asyncio.wait_for(self.reader.readexactly(n), timeout=self.timeout)
        except asyncio.TimeoutError:
            raise asyncio.IncompleteReadError(b'', n)

    async def readline(self):
        """
        reads from ser2net port until \n occurs
        :return:
        """
        if not self.reader:
            await self.open()
        try:
            msg = await asyncio.wait_for(self.reader.readline(), timeout=self.timeout)
        except asyncio.TimeoutError:
            msg = b''
        return msg



