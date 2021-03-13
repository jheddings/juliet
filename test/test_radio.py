import logging
import serial
import unittest
import time

import juliet

# keep logging output to a minumim for testing
logging.basicConfig(level=logging.FATAL)

################################################################################
class RadioCommTest(unittest.TestCase):

    inbox = None

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
    def recv_msg(self, radio, data):
        msg = str(data, 'utf-8')

        if self.inbox is None:
            self.inbox = [ msg ]
        else:
            self.inbox.append(msg)

    #---------------------------------------------------------------------------
    def test_BasicReadTest(self):
        self.inbox = None
        my_txt = 'hello world!'

        self.comm.write(bytes(my_txt, 'utf-8'))

        # sleep long enough for the receive thread to wake up
        time.sleep(3)

        self.assertEqual(1, len(self.inbox))
        self.assertEqual(my_txt, self.inbox[0])

    #---------------------------------------------------------------------------
    def test_ReadMultiLineText(self):
        self.inbox = None

        self.comm.write(bytes('hello\n', 'utf-8'))
        self.comm.write(bytes('world\n', 'utf-8'))

        # sleep long enough for the receive thread to wake up
        time.sleep(3)

        self.assertEqual(2, len(self.inbox))
        self.assertEqual('hello\n', self.inbox[0])
        self.assertEqual('world\n', self.inbox[1])

