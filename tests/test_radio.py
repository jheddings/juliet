import os
import time
import unittest

import serial

import juliet.radio


class InboxMixin:
    inbox = None

    def recv_msg(self, radio, data):
        if self.inbox is None:
            self.inbox = [data]
        else:
            self.inbox.append(data)

    def check_inbox(self, *expected):
        assert self.inbox is not None
        assert len(expected) == len(self.inbox)

        for idx in range(len(expected)):
            expect = expected[idx]
            msg = self.inbox[idx]
            assert expect == msg


class RadioLoopTest(unittest.TestCase, InboxMixin):
    def setUp(self):
        self.radio = juliet.radio.RadioLoop()
        self.radio.on_recv += self.recv_msg

    def tearDown(self):
        self.radio.close()

    def test_basic_radio_read(self):
        self.inbox = None
        text = "hello world!"
        self.radio.send(text)
        self.check_inbox(text)


class RadioCommTest(unittest.TestCase, InboxMixin):
    def setUp(self):
        if not os.path.exists("/dev/ttyr2"):
            raise unittest.SkipTest("unable to find serial port for test")

        self.comm = serial.Serial("/dev/ttyr2", timeout=1)

        self.radio = juliet.radio.RadioComm("/dev/ptyr2")
        self.radio.on_recv += self.recv_msg

    def tearDown(self):
        self.radio.close()
        self.comm.close()

    def test_basic_comm_read(self):
        self.inbox = None
        text = "hello world!"
        data = bytes(text, "utf-8")

        self.comm.write(data)

        time.sleep(2)  # yield to recv thread

        self.check_inbox(data)

    def test_read_multiline_text(self):
        self.inbox = None

        self.comm.write(bytes("hello\n", "utf-8"))
        self.comm.write(bytes("world\n", "utf-8"))

        time.sleep(2)  # yield to recv thread

        self.check_inbox(bytes("hello\nworld\n", "utf-8"))

    def test_multi_write(self):
        self.inbox = None

        self.comm.write(bytes("hello\n", "utf-8"))
        time.sleep(2)  # yield to recv thread

        self.comm.write(bytes("world\n", "utf-8"))
        time.sleep(2)  # yield to recv thread

        self.check_inbox(bytes("hello\n", "utf-8"), bytes("world\n", "utf-8"))
