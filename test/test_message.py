import logging
import unittest
import string
import os

from juliet.message import TextMessage, CompressedTextMessage, ChannelMessage
from juliet.message import FileMessage

# keep logging output to a minumim for testing
logging.basicConfig(level=logging.FATAL)

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

