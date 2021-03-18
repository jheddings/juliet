import serial
import unittest
import time

import juliet.radio

################################################################################
class InboxMixin(object):

    inbox = None

    #---------------------------------------------------------------------------
    def recv_msg(self, radio, data):
        if self.inbox is None:
            self.inbox = [ data ]
        else:
            self.inbox.append(data)

    #---------------------------------------------------------------------------
    def check_inbox(self, *expected):
        self.assertIsNotNone(self.inbox)
        self.assertEqual(len(expected), len(self.inbox))

        for idx in range(len(expected)):
            expect = expected[idx]
            msg = self.inbox[idx]
            self.assertEqual(expect, msg)

################################################################################
class RadioLoopTest(unittest.TestCase, InboxMixin):

    #---------------------------------------------------------------------------
    def setUp(self):
        self.radio = juliet.radio.RadioLoop()
        self.radio.on_recv += self.recv_msg

    #---------------------------------------------------------------------------
    def tearDown(self):
        self.radio.close()

    #---------------------------------------------------------------------------
    def test_BasicReadTest(self):
        self.inbox = None
        text = 'hello world!'
        self.radio.send(text)
        self.check_inbox(text)

################################################################################
class RadioCommTest(unittest.TestCase, InboxMixin):

    #---------------------------------------------------------------------------
    def setUp(self):
        self.comm = serial.Serial('/dev/ttyr2', timeout=1)

        self.radio = juliet.radio.RadioComm('/dev/ptyr2')
        self.radio.on_recv += self.recv_msg

    #---------------------------------------------------------------------------
    def tearDown(self):
        self.radio.close()
        self.comm.close()

    #---------------------------------------------------------------------------
    def test_BasicReadTest(self):
        self.inbox = None
        text = 'hello world!'
        data = bytes(text, 'utf-8')

        self.comm.write(data)

        # sleep long enough for the receive thread to wake up
        time.sleep(3)

        self.check_inbox(data)

    #---------------------------------------------------------------------------
    def test_ReadMultiLineText(self):
        self.inbox = None

        self.comm.write(bytes('hello\nworld\n', 'utf-8'))

        # sleep long enough for the receive thread to wake up
        time.sleep(3)

        self.check_inbox(
            bytes('hello\n', 'utf-8'),
            bytes('world\n', 'utf-8')
        )

