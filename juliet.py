#!/usr/bin/env python3

# juliet - a simple 2-way serial message client

import os
import re
import queue
import threading
import binascii
import zlib
import base64
import time
import logging
import serial
import blessed

from datetime import datetime, timezone

packed_msg_re = re.compile(r'^>>(?P<ver>[a-fA-F0-9]+):(?P<crc>[a-zA-Z0-9]+):(?P<sender>[a-zA-Z0-9~/=+_-]+)?:(?P<time>[0-9]{14})?:(?P<msg>.+)(?!\\):(?P<sig>[a-zA-Z0-9]+)?<<$')

################################################################################
# modified from https://gist.github.com/oysstu/68072c44c02879a2abf94ef350d1c7c6
def crc16(data, crc=0xFFFF, poly=0x1021):
    if isinstance(data, str):
        data = bytes(data, 'utf-8')

    data = bytearray(data)

    for b in data:
        cur_byte = 0xFF & b
        for _ in range(0, 8):
            if (crc & 0x0001) ^ (cur_byte & 0x0001):
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
            cur_byte >>= 1

    crc = (~crc & 0xFFFF)
    crc = (crc << 8) | ((crc >> 8) & 0xFF)

    return crc & 0xFFFF

################################################################################
# modified from https://stackoverflow.com/a/2022629/197772
class Event(list):

    #---------------------------------------------------------------------------
    def __iadd__(self, handler):
        self.append(handler)
        return self

    #---------------------------------------------------------------------------
    def __isub__(self, handler):
        self.remove(handler)
        return self

    #---------------------------------------------------------------------------
    def __call__(self, *args, **kwargs):
        for handler in self:
            handler(*args, **kwargs)

    #---------------------------------------------------------------------------
    def __repr__(self):
        return "Event(%s)" % list.__repr__(self)

################################################################################
class Message(object):

    version = None

    #---------------------------------------------------------------------------
    def __init__(self, content, sender=None, signature=None, timestamp=None):
        self.content = content
        self.sender = sender
        self.signature = signature

        if timestamp is None:
            self.timestamp = datetime.now(tz=timezone.utc)
        else:
            self.timestamp = timestamp.astimezone(timezone.utc)

        # juliet messages are only accurate to the second...
        self.timestamp = self.timestamp.replace(microsecond=0)

        self.logger = logging.getLogger('juliet.Message')
        self.logger.debug('new message: 0x%04X', self.checksum())

    #---------------------------------------------------------------------------
    # sign this message with the given private key
    def sign(self, privkey):
        return None

    #---------------------------------------------------------------------------
    # confirm the signature of the message
    def verify(self, pubkey):
        return None

    #---------------------------------------------------------------------------
    # confirm the integrity of the message
    def is_valid(self):
        return None

    #---------------------------------------------------------------------------
    def checksum(self):
        crc = crc16(self.content)

        # use a string representation with the correct precision
        tstamp = self.timestamp.strftime('%Y%m%d%H%M%S')
        crc = crc16(tstamp, crc)

        if self.sender is not None:
            crc = crc16(self.sender, crc)

        if self.signature is not None:
            crc = crc16(self.signature, crc)

        return crc

    #---------------------------------------------------------------------------
    def pack(self):
        sender = '' if self.sender is None else self.sender
        sig = '' if self.signature is None else self.signature
        tstamp = self.timestamp.strftime('%Y%m%d%H%M%S')
        crc = format(self.checksum(), '04X')

        version = format(self.version, 'X')
        content = self.pack_content()

        text = f'>>{version}:{crc}:{sender}:{tstamp}:{content}:{sig}<<'
        data = bytes(text, 'utf-8')

        return data

    #---------------------------------------------------------------------------
    def unpack(data):
        if data is None or len(data) == 0:
            return None

        # XXX prefer to data.split(b':') and work with parts
        # XXX - need to check for header and footer
        # XXX - how to handle : in the content?

        try:
            text = str(data, 'utf-8')
        except UnicodeDecodeError as ude:
            return None

        match = packed_msg_re.match(text)
        if match is None or match is False:
            print('NO MATCH')
            return None

        content = match.group('msg')
        version = int(match.group('ver'), 16)

        if version == 0:
            msg = TextMessage(content=content)
        elif version == 1:
            msg = CompressedTextMessage(content=content)
        else:
            raise Exception('unsupported version')

        checksum = int(match.group('crc'), 16)
        # TODO confirm checksum - should we allow "invalid" messages?

        # timestamps are in UTC
        tstamp = datetime.strptime(match.group('time'), '%Y%m%d%H%M%S')
        tstamp = tstamp.replace(tzinfo=timezone.utc)

        msg.sender = match.group('sender')
        msg.signature = match.group('sig')
        msg.content = msg.unpack_content()

        return msg

    #---------------------------------------------------------------------------
    def __hash__(self):
        return self.checksum()

    #---------------------------------------------------------------------------
    def __eq__(self, other):
        if type(other) is type(self):
            return (
                self.content == other.content
                and self.sender == other.sender
                and self.timestamp == other.timestamp
                and self.signature == other.signature
            )

        return NotImplemented

################################################################################
class TextMessage(Message):

    version = 0

    #---------------------------------------------------------------------------
    def pack_content(self):
        return self.content.replace(':', '\\:')

    #---------------------------------------------------------------------------
    def unpack_content(self):
        return self.content.replace('\\:', ':')

################################################################################
# content is compressed and base-64 encoded
class CompressedTextMessage(Message):

    version = 1

    #---------------------------------------------------------------------------
    def pack_content(self):
        data = self.content.encode('utf-8')
        compressed = zlib.compress(data)
        b64 = base64.b64encode(compressed)
        return str(b64, 'ascii')

    #---------------------------------------------------------------------------
    def unpack_content(self):
        b64 = bytes(self.content, 'ascii')
        compressed = base64.b64decode(b64)
        data = zlib.decompress(compressed)
        return data.decode('utf-8')

################################################################################
# content contains identifier to previous message (sender+timestamp)
class ThreadedMessage(Message):
    version = 2

################################################################################
# content contains a name and base-64 content from a file
class FileMessage(Message):
    version = 3

################################################################################
# Events => Handler Function
#   subscribe => func(radio, msg)
class MessageBroker(object):

    #---------------------------------------------------------------------------
    def __init__(self, radio):
        self.radio = radio

        self.subscribe = Event()

        radio.on_recv += self._radio_recv

        self.logger = logging.getLogger('juliet.MessageBroker')

    #---------------------------------------------------------------------------
    def publish(self, msg):
        data = msg.pack()
        self.radio.send(data)

    #---------------------------------------------------------------------------
    def _radio_recv(self, radio, data):
        msg = Message.unpack(data)

        if msg is not None:
            self.subscribe(this, msg)
            self.logger.debug('received message -- %s', msg[:10])

################################################################################
# Events => Handler Function
#   on_xmit => func(radio, data)
#   on_recv => func(radio, data)
class RadioComm(object):

    #---------------------------------------------------------------------------
    def __init__(self, serial_port, baud_rate=9600):
        self.logger = logging.getLogger('juliet.RadioComm')
        self.logger.debug('opening radio on %s', serial_port)

        self.comm = serial.Serial(serial_port, baud_rate, timeout=1)
        self.comm_lock = threading.Lock()

        self.workers_active = True

        # initialize transmitter event / thread / queue
        self.xmit_queue = queue.Queue()
        self.on_xmit = Event()
        self.xmit_thread = threading.Thread(target=self._xmit_worker, daemon=True)
        self.xmit_thread.start()

        # initialize receiver event / thread
        self.on_recv = Event()
        self.recv_thread = threading.Thread(target=self._recv_worker, daemon=True)
        self.recv_thread.start()

        self.logger.info('Radio online -- %s', serial_port)

    #---------------------------------------------------------------------------
    def send(self, data):
        if data is None or len(data) == 0:
            return False

        self.logger.debug('queueing XMIT message -- %s...', data[:10])
        self.xmit_queue.put(data)

        return True

    #---------------------------------------------------------------------------
    def close(self):
        self.logger.debug('closing radio comms...')
        self.workers_active = False

        # TODO support timeouts on thread joins

        self.logger.debug('- waiting for transmitter...')
        self.xmit_thread.join()

        self.logger.debug('- waiting for receiver...')
        self.recv_thread.join()

        self.logger.debug('- closing serial port...')
        self.comm.close()

        self.logger.info('Radio offline.')

    #---------------------------------------------------------------------------
    def _recv_worker(self):
        while self.workers_active:
            data = None

            with self.comm_lock:
                data = self.comm.readline()

            if data and len(data) > 0:
                self.logger.debug('recv -- %s', data)
                self.on_recv(self, data)

            # unlike the xmit thread, we do a quick sleep here as a yield for
            # outgoing messages and quickly resume looking for incoming data

            time.sleep(0)

    #---------------------------------------------------------------------------
    def _xmit_worker(self):
        while self.workers_active:
            try:
                data = self.xmit_queue.get(False)
                self.logger.debug('xmit -- %s', data)

                with self.comm_lock:
                    self.comm.write(data)

                self.on_xmit(self, data)

            # raised if the queue is empty during timeout
            except queue.Empty:
                pass

            # the sleep here serves two purposes:
            # - yield to the recv thread
            # - limit transmission rate

            time.sleep(1)

################################################################################
class Console(object):

    #---------------------------------------------------------------------------
    def __init__(self, radio, terminal=None):
        self.radio = radio
        self.terminal = blessed.Terminal() if terminal is None else terminal

        self.broker = MessageBroker(radio)
        self.broker.subscribe += self.recv_msg

        #self.radio.on_recv += self.recv_msg
        #self.radio.on_xmit += self.xmit_msg

        self.active = False

        self.logger = logging.getLogger('juliet.Console')

    #---------------------------------------------------------------------------
    def run(self):
        self.active = True

        try:
            self._run_loop()
        except EOFError:
            self.logger.info('End of input')

        self.active = False

    #---------------------------------------------------------------------------
    def _run_loop(self):
        self.logger.debug('entering run loop')

        while self.active:
            text = None

            try:

                text = input(': ')

            # ignore ^C - cancel current msg
            except KeyboardInterrupt:
                print()
                continue

            msg = Message(content=text)
            self.broker.publish(msg)

            #data = bytes(text, 'utf-8')
            #self.radio.send(data)

        self.logger.debug('exiting run loop')

    #---------------------------------------------------------------------------
    def xmit_msg(self, radio, msg):
        print(f'\n> {msg}\n: ', end='')

    #---------------------------------------------------------------------------
    def recv_msg(self, radio, msg):
        print(f'\n< {msg}\n: ', end='')

################################################################################
class Reflector(object):

    #---------------------------------------------------------------------------
    def __init__(self, broker):
        self.broker = broker

        # TODO watch for messages from broker and relay to reflector (server)

################################################################################
def parse_args():
    import argparse

    argp = argparse.ArgumentParser(description='juliet: a simple 2-way serial text client')

    argp.add_argument('--config', default='juliet.cfg',
                      help='configuration file (default: juliet.cfg)')

    # juliet.cfg overrides these values
    argp.add_argument('--port', help='serial port for comms')
    argp.add_argument('--baud', help='baud rate for comms')

    return argp.parse_args()

################################################################################
def load_config(args):
    import yaml
    import logging.config

    try:
        from yaml import CLoader as YamlLoader
    except ImportError:
        from yaml import Loader as YamlLoader

    config_file = args.config

    if not os.path.exists(config_file):
        print(f'ERROR: config file does not exist: {config_file}')
        return None

    with open(config_file, 'r') as fp:
        conf = yaml.load(fp, Loader=YamlLoader)

        # determine if logging is already configured...
        root_logger = logging.getLogger()
        if not root_logger.hasHandlers():
            if 'logging' in conf:
                logging.config.dictConfig(conf['logging'])
            else:
                logging.basicConfig(level=logging.WARN)

    # TODO error checking on parameters

    if 'port' not in conf:
        conf['port'] = args.port

    if 'baud' not in conf:
        conf['baud'] = args.baud

    return conf

################################################################################
## MAIN ENTRY

if __name__ == '__main__':
    args = parse_args()
    conf = load_config(args)

    radio = RadioComm(
        serial_port=conf['port'],
        baud_rate=conf['baud']
    )

    term = blessed.Terminal()
    jules = Console(radio, term)

    jules.run()

    radio.close()

