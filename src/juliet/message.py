##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import re
import zlib
import base64

from datetime import datetime, timezone

packed_msg_re = re.compile(r'^>>(?P<ver>[a-fA-F0-9]+):(?P<crc>[a-zA-Z0-9]+):(?P<sender>[a-zA-Z0-9~/=+_$@#*&%!|-]+)?:(?P<time>[0-9]{14})?:(?P<msg>.+)(?!\\):(?P<sig>[a-zA-Z0-9]+)?<<$')

################################################################################
def format_timestamp(tstamp):
    return tstamp.strftime('%Y%m%d%H%M%S')

def parse_timestamp(string):
    return datetime.strptime(string, '%Y%m%d%H%M%S')

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

        if version == TextMessage.version:
            msg = TextMessage(content)
        elif version == CompressedTextMessage.version:
            msg = CompressedTextMessage(content)
        elif version == ChannelMessage.version:
            msg = ChannelMessage(content)
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
class ChannelMessage(TextMessage):

    version = 3

    #---------------------------------------------------------------------------
    def __init__(self, content, channel=None, sender=None, signature=None, timestamp=None):
        TextMessage.__init__(self, content, sender=sender, signature=signature, timestamp=timestamp)

        self.channel = channel

    #---------------------------------------------------------------------------
    def pack_content(self):
        text = self.channel + ' ' + self.content
        return text.replace(':', '\\:')

    #---------------------------------------------------------------------------
    def unpack_content(self):
        text = self.content.replace('\\:', ':')
        self.channel, self.content = text.split(' ', 1)

