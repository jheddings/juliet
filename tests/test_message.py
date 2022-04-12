import logging
import string
import unittest

from juliet.message import (
    ChannelMessage,
    CompressedTextMessage,
    FileMessage,
    MessageBuffer,
    TextMessage,
)

# keep logging output to a minumim for testing
logging.basicConfig(level=logging.FATAL)


class MessageBufferTest(unittest.TestCase):

    inbox = None

    def setUp(self):
        self.msgbuf = MessageBuffer()
        self.msgbuf.on_message += self.recv_msg

    def recv_msg(self, msgbuf, msg):
        if self.inbox is None:
            self.inbox = [msg]
        else:
            self.inbox.append(msg)

    def check_inbox(self, *expected):
        assert self.inbox is not None
        assert len(expected) == len(self.inbox)

        for idx in range(len(expected)):
            expect = expected[idx]
            msg = self.inbox[idx]
            assert expect == msg

    def test_basic_parse_message(self):
        self.inbox = None
        self.msgbuf.reset()

        data = b">>0:36FB:unittest:20210319143703:hello world:<<"
        self.msgbuf.append(data)

        assert len(self.inbox) == 1

        msg = self.inbox[0]

        assert msg.sender == "unittest"
        assert msg.content == "hello world"

    def test_split_message(self):
        self.inbox = None
        self.msgbuf.reset()

        self.msgbuf.append(b">>0:36FB:unittest:20210")
        assert self.inbox is None

        self.msgbuf.append(b"319143703:hello world:<<")
        assert len(self.inbox) == 1

        msg = self.inbox[0]

        assert msg.sender == "unittest"
        assert msg.content == "hello world"

    def test_handle_multiple_messages(self):
        self.inbox = None
        self.msgbuf.reset()

        data = b">>0:59F6:unittest:20210319145252:hello:<<>>0:A2F3:unittest:20210319145320:world:<<>>BAD"
        self.msgbuf.append(data)

        assert self.inbox is not None
        assert len(self.inbox) == 2

        msg1 = self.inbox[0]
        msg2 = self.inbox[1]

        assert msg1.content == "hello"
        assert msg2.content == "world"

    def test_restart_message(self):

        self.msgbuf.append(b">>0::unitt>>0:36FB:unittest:20210")
        assert self.inbox is None

        self.msgbuf.append(b"319143703:hello world:<<")
        assert self.inbox is not None
        assert len(self.inbox) == 1

        msg = self.inbox[0]

        assert msg.sender == "unittest"
        assert msg.content == "hello world"
        assert len(self.msgbuf.buffer) == 0

    def test_bad_message(self):
        self.inbox = None
        self.msgbuf.reset()

        data = b">>B:unittest:202103:blue:<<"
        self.msgbuf.append(data)

        assert self.inbox is None


class MessageTest(unittest.TestCase):
    def test_printable_characters(self):
        text = string.printable
        self.check_standard_text_msg(text)

    def test_standard_ascii(self):
        text = "".join([chr(ch) for ch in range(32, 128)])
        self.check_standard_text_msg(text)

    def test_extended_ascii(self):
        text = "".join([chr(ch) for ch in range(128, 256)])
        self.check_standard_text_msg(text)

    def test_utf8(self):
        text = "нєℓℓσ ωσяℓ∂"
        self.check_standard_text_msg(text)

        text = "你好世界"
        self.check_standard_text_msg(text)

        text = "नमस्ते दुनिया"
        self.check_standard_text_msg(text)

        text = "مرحبا بالعالم"
        self.check_standard_text_msg(text)

        text = "😀🙃😳🤔🤐🤬👻☠☃💯"
        self.check_standard_text_msg(text)

    def test_protocol_characters(self):
        text = "Lorem ipsum:dolorsit:amet"
        self.check_standard_text_msg(text)

        text = ":Lorem ipsum dolor sit amet"
        self.check_standard_text_msg(text)

        text = "Lorem ipsum dolor sit amet:"
        self.check_standard_text_msg(text)

        text = "Lorem ipsum dolor sit :amet:<<"
        self.check_standard_text_msg(text)

        text = "<<Lorem ipsum dolor sit amet>>"
        self.check_standard_text_msg(text)

        text = ",Lorem|ipsum:dolor+sit<<amet"
        self.check_standard_text_msg(text)

    def test_compressed_text_message(self):
        text = string.printable * 4

        orig = CompressedTextMessage(text)
        packed = orig.pack()
        copy = CompressedTextMessage.unpack(packed)

        assert orig == copy

    def test_channel_message(self):
        text = "hello world"
        channel = "#general"

        orig = ChannelMessage(text, channel)
        packed = orig.pack()
        copy = ChannelMessage.unpack(packed)

        assert copy.channel == "#general"
        assert copy.content == "hello world"

        assert orig == copy

    def test_file_message(self):
        with open(__file__) as fp:
            content = fp.read()

        orig = FileMessage(content=content)
        packed = orig.pack()
        copy = FileMessage.unpack(packed)

        assert orig == copy

        assert orig.content == content
        assert content == copy.content

    def check_standard_text_msg(self, text):
        orig = TextMessage(text, sender="unittest")
        packed = orig.pack()
        copy = TextMessage.unpack(packed)

        assert packed is not None
        assert orig is not None
        assert copy is not None

        assert text == orig.content
        assert text == copy.content

        assert orig == copy
