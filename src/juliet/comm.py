# juliet - an IRC bot for relaying to radio networks

import re
import queue
import threading
import time
import logging
import serial

from datetime import datetime, timezone

from .event import Event

packed_msg_re = re.compile(r'^>>(?P<ver>[a-fA-F0-9]+):(?P<crc>[a-zA-Z0-9]+):(?P<sender>[a-zA-Z0-9~/=+_$@#*&%!|-]+)?:(?P<time>[0-9]{14})?:(?P<msg>.+)(?!\\):(?P<sig>[a-zA-Z0-9]+)?<<$')

################################################################################
safe_filename_chars = '.-_ '

def make_safe_filename(unsafe):
    if unsafe is None or len(unsafe) == 0:
        return None

    safe = ''.join([c for c in unsafe if c.isalnum() or c in safe_filename_chars])

    return safe.strip()

################################################################################
def format_timestamp(tstamp):
    return tstamp.strftime('%Y%m%d%H%M%S')

################################################################################
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
# Events => Handler Function
#   on_xmit => func(radio, data)
#   on_recv => func(radio, data)
class CommBase(object):

    #---------------------------------------------------------------------------
    def __init__(self):
        self.on_xmit = Event()
        self.on_recv = Event()

        self.logger = logging.getLogger('juliet.CommBase')

    #---------------------------------------------------------------------------
    def send(self, data): pass

    #---------------------------------------------------------------------------
    def close(self): pass

################################################################################
class CommLoop(CommBase):

    #---------------------------------------------------------------------------
    def __init__(self):
        CommBase.__init__(self)

        self.logger = logging.getLogger('juliet.CommLoop')

    #---------------------------------------------------------------------------
    def send(self, data):
        self.on_xmit(self, data)
        self.logger.debug('send -- %s', data)
        self.on_recv(self, data)

################################################################################
class RadioComm(CommBase):

    #---------------------------------------------------------------------------
    def __init__(self, serial_port, baud_rate=9600):
        CommBase.__init__(self)

        self.logger = logging.getLogger('juliet.RadioComm')
        self.logger.debug('opening radio on %s', serial_port)

        self.comm = serial.Serial(serial_port, baud_rate, timeout=1)
        self.comm_lock = threading.Lock()

        self.workers_active = True

        # initialize transmitter event / thread / queue
        self.xmit_queue = queue.Queue()
        self.xmit_thread = threading.Thread(target=self._xmit_worker, daemon=True)
        self.xmit_thread.start()

        # initialize receiver event / thread
        self.recv_thread = threading.Thread(target=self._recv_worker, daemon=True)
        self.recv_thread.start()

        self.logger.info('Radio online -- %s', serial_port)

    #---------------------------------------------------------------------------
    def send(self, data):
        if data is None or len(data) == 0:
            return False

        self.logger.debug('queueing XMIT message -- %s...', data[:10])
        self.xmit_queue.put(data)

        return True

    #---------------------------------------------------------------------------
    def close(self):
        self.logger.debug('closing radio comms...')
        self.workers_active = False

        # TODO support timeouts on thread joins

        self.logger.debug('- waiting for transmitter...')
        self.xmit_thread.join()

        self.logger.debug('- waiting for receiver...')
        self.recv_thread.join()

        self.logger.debug('- closing serial port...')
        self.comm.close()

        self.logger.info('Radio offline.')

    #---------------------------------------------------------------------------
    def _recv_worker(self):
        while self.workers_active:
            data = None

            with self.comm_lock:
                data = self.comm.readline()

            if data and len(data) > 0:
                self.logger.debug('recv -- %s', data)
                self.on_recv(self, data)

            # unlike the xmit thread, we do a quick sleep here as a yield for
            # outgoing messages and quickly resume looking for incoming data

            time.sleep(0)

    #---------------------------------------------------------------------------
    def _xmit_worker(self):
        while self.workers_active:
            try:
                data = self.xmit_queue.get(False)
                self.logger.debug('xmit -- %s', data)

                with self.comm_lock:
                    self.comm.write(data)

                self.on_xmit(self, data)

            # raised if the queue is empty during timeout
            except queue.Empty:
                pass

            # the sleep here serves two purposes:
            # - yield to the recv thread
            # - limit transmission rate

            time.sleep(1)

