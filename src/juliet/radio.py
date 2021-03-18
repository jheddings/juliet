##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import queue
import threading
import time
import logging
import serial

from .event import Event

################################################################################
# Events => Handler Function
#   on_xmit => func(radio, data)
#   on_recv => func(radio, data)
class RadioBase(object):

    #---------------------------------------------------------------------------
    def __init__(self):
        self.on_xmit = Event()
        self.on_recv = Event()

        self.logger = logging.getLogger('juliet.comm.RadioBase')

    #---------------------------------------------------------------------------
    def send(self, data): pass

    #---------------------------------------------------------------------------
    def close(self): pass

################################################################################
class RadioLoop(RadioBase):

    #---------------------------------------------------------------------------
    def __init__(self):
        RadioBase.__init__(self)

        self.logger = logging.getLogger('juliet.comm.RadioLoop')

    #---------------------------------------------------------------------------
    def send(self, data):
        self.on_xmit(self, data)
        self.logger.debug('send -- %s', data)
        self.on_recv(self, data)

################################################################################
class RadioComm(RadioBase):

    #---------------------------------------------------------------------------
    def __init__(self, serial_port, baud_rate=9600):
        RadioBase.__init__(self)

        self.logger = logging.getLogger('juliet.comm.RadioComm')
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

