import serial
import unittest
import time

import juliet
import util

################################################################################
class CommLoopTest(unittest.TestCase, util.InboxMixin):

    #---------------------------------------------------------------------------
    def setUp(self):
        self.comm = juliet.CommLoop()
        self.comm.on_recv += self.recv_msg

    #---------------------------------------------------------------------------
    def tearDown(self):
        self.comm.close()

    #---------------------------------------------------------------------------
    def test_BasicReadTest(self):
        self.inbox = None
        text = 'hello world!'
        self.comm.send(text)
        self.check_inbox(text)

################################################################################
class RadioCommTest(unittest.TestCase, util.InboxMixin):

    #---------------------------------------------------------------------------
    def setUp(self):
        self.comm = serial.Serial('/dev/ttyr2', timeout=1)

        self.radio = juliet.RadioComm('/dev/ptyr2')
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

