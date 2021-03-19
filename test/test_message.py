import logging
import unittest
import string
import os

from juliet.message import MessageBuffer, TextMessage, CompressedTextMessage
from juliet.message import FileMessage, ChannelMessage

# keep logging output to a minumim for testing
logging.basicConfig(level=logging.FATAL)

################################################################################
class MessageBufferTest(unittest.TestCase):

    inbox = None

    #---------------------------------------------------------------------------
    def setUp(self):
        self.msgbuf = MessageBuffer()
        self.msgbuf.on_message += self.recv_msg

    #---------------------------------------------------------------------------
    def recv_msg(self, msgbuf, msg):
        if self.inbox is None:
            self.inbox = [ msg ]
        else:
            self.inbox.append(msg)

    #---------------------------------------------------------------------------
    def check_inbox(self, *expected):
        self.assertIsNotNone(self.inbox)
        self.assertEqual(len(expected), len(self.inbox))

        for idx in range(len(expected)):
            expect = expected[idx]
            msg = self.inbox[idx]
            self.assertEqual(expect, msg)

    #---------------------------------------------------------------------------
    def test_ParseMessage(self):
        self.inbox = None
        self.msgbuf.reset()

        data = b'>>0:36FB:unittest:20210319143703:hello world:<<'
        self.msgbuf.append(data)

        self.assertEqual(len(self.inbox), 1)

        msg = self.inbox[0]

        self.assertEqual(msg.sender, 'unittest')
        self.assertEqual(msg.content, 'hello world')

    #---------------------------------------------------------------------------
    def test_SplitMessage(self):
        self.inbox = None
        self.msgbuf.reset()

        self.msgbuf.append(b'>>0:36FB:unittest:20210')
        self.assertIsNone(self.inbox)

        self.msgbuf.append(b'319143703:hello world:<<')
        self.assertEqual(len(self.inbox), 1)

        msg = self.inbox[0]

        self.assertEqual(msg.sender, 'unittest')
        self.assertEqual(msg.content, 'hello world')

    #---------------------------------------------------------------------------
    def test_MultipleMessages(self):
        self.inbox = None
        self.msgbuf.reset()

        data = b'>>0:59F6:unittest:20210319145252:hello:<<>>0:A2F3:unittest:20210319145320:world:<<>>BAD'
        self.msgbuf.append(data)

        self.assertIsNotNone(self.inbox)
        self.assertEqual(len(self.inbox), 2)

        msg1 = self.inbox[0]
        msg2 = self.inbox[1]

        self.assertEqual(msg1.content, 'hello')
        self.assertEqual(msg2.content, 'world')

    #---------------------------------------------------------------------------
    def test_RestartMessage(self):

        self.msgbuf.append(b'>>0::unitt>>0:36FB:unittest:20210')
        self.assertIsNone(self.inbox)

        self.msgbuf.append(b'319143703:hello world:<<')
        self.assertEqual(len(self.inbox), 1)

        msg = self.inbox[0]

        self.assertEqual(msg.sender, 'unittest')
        self.assertEqual(msg.content, 'hello world')
        self.assertEqual(len(self.msgbuf.buffer), 0)

    #---------------------------------------------------------------------------
    def test_BadMessage(self):
        self.inbox = None
        self.msgbuf.reset()

        data = b'>>0:36>>B:unittest:202103:blue:<<'
        self.msgbuf.append(data)

        self.assertIsNone(self.inbox)

################################################################################
class MessageTest(unittest.TestCase):

    #---------------------------------------------------------------------------
    def test_PrintableCharacters(self):
        text = string.printable
        self.check_standard_text_msg(text)

    #---------------------------------------------------------------------------
    def test_StandardASCII(self):
        text = ''.join([chr(ch) for ch in range(32, 128)])
        self.check_standard_text_msg(text)

    #---------------------------------------------------------------------------
    def test_ExtendedASCII(self):
        text = ''.join([chr(ch) for ch in range(128, 256)])
        self.check_standard_text_msg(text)

    #---------------------------------------------------------------------------
    def test_UTF8(self):
        text = 'нєℓℓσ ωσяℓ∂'
        self.check_standard_text_msg(text)

        text = '你好世界'
        self.check_standard_text_msg(text)

        text = 'नमस्ते दुनिया'
        self.check_standard_text_msg(text)

        text = 'مرحبا بالعالم'
        self.check_standard_text_msg(text)

        text = '😀🙃😳🤔🤐🤬👻☠☃💯'
        self.check_standard_text_msg(text)

    #---------------------------------------------------------------------------
    def test_SpecialProtocolCharacters(self):
        text = 'Lorem ipsum:dolorsit:amet'
        self.check_standard_text_msg(text)

        text = ':Lorem ipsum dolor sit amet'
        self.check_standard_text_msg(text)

        text = 'Lorem ipsum dolor sit amet:'
        self.check_standard_text_msg(text)

        text = 'Lorem ipsum dolor sit :amet:<<'
        self.check_standard_text_msg(text)

        text = '<<Lorem ipsum dolor sit amet>>'
        self.check_standard_text_msg(text)

        text = ',Lorem|ipsum:dolor+sit<<amet'
        self.check_standard_text_msg(text)

    #---------------------------------------------------------------------------
    def test_CompressedTextMessage(self):
        text = string.printable * 4

        orig = CompressedTextMessage(text)
        packed = orig.pack()
        copy = CompressedTextMessage.unpack(packed)

        self.assertEqual(orig, copy)

    #---------------------------------------------------------------------------
    def test_ChannelMessage(self):
        text = 'hello world'
        channel = '#general'

        orig = ChannelMessage(text, channel)
        packed = orig.pack()
        copy = ChannelMessage.unpack(packed)

        self.assertEqual(copy.channel, '#general')
        self.assertEqual(copy.content, 'hello world')

        self.assertEqual(orig, copy)

    #---------------------------------------------------------------------------
    def test_FileMessage(self):
        with open(__file__) as fp:
            content = fp.read()

        orig = FileMessage(content=content)
        packed = orig.pack()
        copy = FileMessage.unpack(packed)

        self.assertEqual(orig, copy)

        self.assertEqual(orig.content, content)
        self.assertEqual(content, copy.content)

    #---------------------------------------------------------------------------
    def check_standard_text_msg(self, text):
        orig = TextMessage(text, sender='unittest')
        packed = orig.pack()
        copy = TextMessage.unpack(packed)

        self.assertIsNotNone(packed)
        self.assertIsNotNone(orig)
        self.assertIsNotNone(copy)

        self.assertEqual(text, orig.content)
        self.assertEqual(text, copy.content)

        self.assertEqual(orig, copy)

