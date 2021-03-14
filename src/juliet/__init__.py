#!/usr/bin/env python3

# juliet - a mesh IRC server for radio networks

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
import mimetypes

from datetime import datetime, timezone

packed_msg_re = re.compile(r'^>>(?P<ver>[a-fA-F0-9]+):(?P<crc>[a-zA-Z0-9]+):(?P<sender>[a-zA-Z0-9~/=+_$@#*&%!|-]+)?:(?P<time>[0-9]{14})?:(?P<msg>.+)(?!\\):(?P<sig>[a-zA-Z0-9]+)?<<$')

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
def checksum(*parts):
    crc = 0xFFFF

    for part in parts:
        if part is None:
            continue

        crc = crc16(part, crc)

    return crc

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
    def pack(self):
        sender = '' if self.sender is None else self.sender
        tstamp = format_timestamp(self.timestamp)
        sig = '' if self.signature is None else self.signature
        content = self.pack_content()

        crc = checksum(sender, tstamp, content, sig)

        text = f'>>{self.version:X}:{crc:04X}:{sender}:{tstamp}:{content}:{sig}<<'
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
        elif version == 3:
            msg = FileMessage(content=content)
        else:
            raise Exception('unsupported version')

        checksum = int(match.group('crc'), 16)
        # TODO confirm checksum - should we allow "invalid" messages?

        # timestamps are in UTC
        tstamp = parse_timestamp(match.group('time'))
        tstamp = tstamp.replace(tzinfo=timezone.utc)

        msg.sender = match.group('sender')
        msg.signature = match.group('sig')

        msg.unpack_content()

        return msg

    #---------------------------------------------------------------------------
    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return NotImplemented

################################################################################
class CompressedMessage(Message):

    #---------------------------------------------------------------------------
    def compress(self, content):
        data = content.encode('utf-8')
        compressed = zlib.compress(data)
        b64 = base64.b64encode(compressed)
        return str(b64, 'ascii')

    #---------------------------------------------------------------------------
    def decompress(self, content):
        b64 = bytes(content, 'ascii')
        compressed = base64.b64decode(b64)
        data = zlib.decompress(compressed)
        return data.decode('utf-8')

################################################################################
class TextMessage(Message):

    version = 0

    #---------------------------------------------------------------------------
    def pack_content(self):
        return self.content.replace(':', '\\:')

    #---------------------------------------------------------------------------
    def unpack_content(self):
        self.content = self.content.replace('\\:', ':')

################################################################################
class CompressedTextMessage(CompressedMessage):

    version = 1

    #---------------------------------------------------------------------------
    def pack_content(self):
        return self.compress(self.content)

    #---------------------------------------------------------------------------
    def unpack_content(self):
        self.content = self.decompress(self.content)

################################################################################
class ThreadedMessage(Message):

    version = 2
    origin = None

    #---------------------------------------------------------------------------
    def __init__(self, content, origin, sender=None, signature=None, timestamp=None):
        Message.__init__(self, content, sender, signature, timestamp)

        # origin must be properly filled out
        if origin is None or origin.sender is None or origin.timestamp is None:
            raise ValueError('invalid origin for ThreadedMessage')

        self.origin = origin.sender + '+' + format_timestamp(origin.timestamp)

    #---------------------------------------------------------------------------
    def pack_content(self):
        return self.origin + '|' + self.content

    #---------------------------------------------------------------------------
    def unpack_content(self):
        if self.content is None:
            return None

        (origin, content) = self.content.split('|', 1)

        self.origin = origin
        self.content = content

################################################################################
class FileMessage(CompressedMessage):

    version = 3
    filename = None
    mimetype = None

    #---------------------------------------------------------------------------
    def __init__(self, content, filename=None, mimetype=None, sender=None, signature=None, timestamp=None):
        CompressedMessage.__init__(self, content, sender, signature, timestamp)

        self.filename = make_safe_filename(filename)

        if mimetype is None and filename is not None:
            guess = mimetypes.guess_type(filename)
            self.mimetype = guess[0] or 'application/octet-stream'
        else:
            self.mimetype = mimetype

    #---------------------------------------------------------------------------
    def pack_content(self):
        filename = make_safe_filename(self.filename) or ''
        mimetype = self.mimetype or ''
        compressed = self.compress(self.content)
        return filename + '|' + mimetype + '|' + compressed

    #---------------------------------------------------------------------------
    def unpack_content(self):
        (filename, mimetype, compressed) = self.content.split('|', 2)
        self.filename = make_safe_filename(filename)
        self.mimetype = mimetype if len(mimetype) > 0 else None
        self.content = self.decompress(compressed)

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

            msg = TextMessage(content=text)
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

