##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import base64
import logging
import mimetypes
import re
import threading
import zlib
from datetime import datetime, timezone

from .event import Event

msg_frame_re = re.compile(rb">>[^><]+<<")
packed_msg_re = re.compile(
    r"^>>(?P<ver>[a-fA-F0-9]+):(?P<crc>[a-zA-Z0-9]+):(?P<sender>[a-zA-Z0-9~/=+_$@#*&%!|-]+)?:(?P<time>[0-9]{14})?:(?P<msg>.+)(?!\\):(?P<sig>[a-zA-Z0-9]+)?<<$"
)

DEFAULT_MAX_BUF_LEN = 5 * 1024 * 1024

## FUTURE MESSAGE TYPES:
#  - Position: current object position
#  - Weather: current observed weather
#  - APRS: maybe just support APRS frames?


def format_timestamp(tstamp):
    tstamp = tstamp.astimezone(tz=timezone.utc)
    return tstamp.strftime("%Y%m%d%H%M%S")


def parse_timestamp(string):
    tstamp = datetime.strptime(string, "%Y%m%d%H%M%S")
    return tstamp.replace(tzinfo=timezone.utc)


# modified from https://gist.github.com/oysstu/68072c44c02879a2abf94ef350d1c7c6
def crc16(data, crc=0xFFFF, poly=0x1021):
    if isinstance(data, str):
        data = bytes(data, "utf-8")

    data = bytearray(data)

    for b in data:
        cur_byte = 0xFF & b
        for _ in range(0, 8):
            if (crc & 0x0001) ^ (cur_byte & 0x0001):
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
            cur_byte >>= 1

    crc = ~crc & 0xFFFF
    crc = (crc << 8) | ((crc >> 8) & 0xFF)

    return crc & 0xFFFF


def checksum(*parts):
    crc = 0xFFFF

    for part in parts:
        if part is None:
            continue

        if len(part) == 0:
            continue

        crc = crc16(part, crc)

    return crc


safe_filename_chars = ".-_ "


def make_safe_filename(unsafe):
    if unsafe is None or len(unsafe) == 0:
        return None

    safe = "".join([c for c in unsafe if c.isalnum() or c in safe_filename_chars])

    return safe.strip()


# make text safe for transmitting (mostly protocol chracters)...

char_entities = {
    ":": "%3A",
    ">": "%3E",
    "<": "%3C",
    "\r": "%0D",
    "\n": "%0A",
}


def char_escape(text):
    return "".join(char_entities.get(ch, ch) for ch in text)


# XXX as a shortcut use standard decode from urllib...  we use the
# above table to keep messages short and easier to read in plain text

import urllib.parse


def char_unescape(text):
    return urllib.parse.unquote(text)


class MessageBuffer(object):
    def __init__(self, maxlen=DEFAULT_MAX_BUF_LEN):
        self.buffer = b""
        self.maxlen = maxlen

        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__).getChild("MessageBuffer")

        self.on_message = Event()

    def reset(self):
        with self.lock:
            self.buffer = b""

    def append(self, data):
        with self.lock:
            self.logger.debug("adding %d bytes to buffer", len(data))

            self.buffer += data
            self.parse_buffer()

            # keep the buffer below our max length...
            if len(self.buffer) > self.maxlen:
                trim_buff = -1 * self.maxlen
                self.buffer = self.buffer[trim_buff:]

    def parse_buffer(self):
        messages = []

        with self.lock:
            self.logger.debug("parsing buffer -- %d bytes", len(self.buffer))
            frame = self.next_frame()

            while frame:
                try:
                    msg = Message.unpack(frame)
                    messages.append(msg)
                    self.on_message(self, msg)
                except ValueError:
                    self.logger.warning("Invalid message frame -- %s...", frame[:10])

                frame = self.next_frame()

        return messages

    def next_frame(self):
        frame = None

        with self.lock:
            self.logger.debug("NEXT: %s", self.buffer)

            match = msg_frame_re.search(self.buffer)

            if match:
                frame = match.group(0)
                eom = match.end()
                self.buffer = self.buffer[eom:]

        return frame


class Message(object):

    version = None

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

    # sign this message with the given private key
    def sign(self, privkey):
        return None

    # confirm the signature of the message
    def verify(self, pubkey):
        return None

    # confirm the integrity of the message
    def confirm(self, crc):
        return None

    def pack(self):
        sender = "" if self.sender is None else self.sender
        tstamp = format_timestamp(self.timestamp)
        sig = "" if self.signature is None else self.signature
        content = self.pack_content()
        crc = checksum(sender, tstamp, content, sig)

        text = f">>{self.version:X}:{crc:04X}:{sender}:{tstamp}:{content}:{sig}<<"

        return bytes(text, "utf-8")

    @classmethod
    def unpack(cls, data, verify_crc=True):
        if data is None or len(data) == 0:
            return None

        try:
            text = str(data, "utf-8")
        except UnicodeDecodeError:
            return None

        match = packed_msg_re.match(text)
        if match is None or match is False:
            raise ValueError("invalid message data")

        sender = match.group("sender")
        content = match.group("msg")
        tstamp = match.group("time")
        sig = match.group("sig")

        if verify_crc:
            crc_orig = int(match.group("crc"), 16)
            crc_calc = checksum(sender, tstamp, content, sig)

            if crc_orig != crc_calc:
                raise ValueError("checksum does not match")

        version = int(match.group("ver"), 16)

        if version == TextMessage.version:
            msg = TextMessage(content)
        elif version == CompressedTextMessage.version:
            msg = CompressedTextMessage(content)
        elif version == ChannelMessage.version:
            msg = ChannelMessage(content)
        elif version == FileMessage.version:
            msg = FileMessage(content)
        else:
            raise Exception("unsupported version")

        msg.sender = sender
        msg.signature = sig
        msg.timestamp = parse_timestamp(tstamp)

        msg.unpack_content()

        return msg

    def __eq__(self, other):
        if type(other) is type(self):
            return self.__dict__ == other.__dict__
        return NotImplemented


class CompressedMessage(Message):
    def compress(self, content):
        data = content.encode("utf-8")
        compressed = zlib.compress(data)
        b64 = base64.b64encode(compressed)
        return str(b64, "ascii")

    def decompress(self, content):
        b64 = bytes(content, "ascii")
        compressed = base64.b64decode(b64)
        data = zlib.decompress(compressed)
        return data.decode("utf-8")


class TextMessage(Message):

    version = 0

    def pack_content(self):
        return char_escape(self.content)

    def unpack_content(self):
        self.content = char_unescape(self.content)


class CompressedTextMessage(CompressedMessage):

    version = 1

    def pack_content(self):
        return self.compress(self.content)

    def unpack_content(self):
        self.content = self.decompress(self.content)


class ChannelMessage(TextMessage):

    version = 3

    def __init__(
        self, content, channel=None, sender=None, signature=None, timestamp=None
    ):
        super().__init__(
            content, sender=sender, signature=signature, timestamp=timestamp
        )

        self.channel = channel

    def pack_content(self):
        text = self.channel + " " + self.content
        return char_escape(text)

    def unpack_content(self):
        text = char_unescape(self.content)
        self.channel, self.content = text.split(" ", 1)


class FileMessage(CompressedMessage):

    version = 7
    filename = None
    mimetype = None

    def __init__(
        self,
        content,
        filename=None,
        mimetype=None,
        sender=None,
        signature=None,
        timestamp=None,
    ):
        super().__init__(content, sender, signature, timestamp)

        self.filename = make_safe_filename(filename)

        if mimetype is None and filename is not None:
            guess = mimetypes.guess_type(filename)
            self.mimetype = guess[0] or "application/octet-stream"
        else:
            self.mimetype = mimetype

    def pack_content(self):
        filename = make_safe_filename(self.filename) or ""
        mimetype = self.mimetype or ""
        compressed = self.compress(self.content)
        return filename + "|" + mimetype + "|" + compressed

    def unpack_content(self):
        (filename, mimetype, compressed) = self.content.split("|", 2)
        self.filename = make_safe_filename(filename)
        self.mimetype = mimetype if len(mimetype) > 0 else None
        self.content = self.decompress(compressed)
