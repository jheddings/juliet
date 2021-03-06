#!/usr/bin/env python3

# juliet - the simple 2-way serial text client

import os
import queue
import threading
import time
import logging
import serial

################################################################################
# modified from https://stackoverflow.com/a/2022629/197772
class Event(list):

    #---------------------------------------------------------------------------
    def __init__(self):
        self.logger = logging.getLogger('juliet.Event')

    #---------------------------------------------------------------------------
    def __iadd__(self, handler):
        self.append(handler)
        return self

    #---------------------------------------------------------------------------
    def __isub__(self, handler):
        self.remove(handler)
        return self

    #---------------------------------------------------------------------------
    def __call__(self, *args, **kwargs):
        for handler in self:
            handler(*args, **kwargs)

    #---------------------------------------------------------------------------
    def __repr__(self):
        return "Event(%s)" % list.__repr__(self)

################################################################################
# Events => Handler Function
#   on_xmit => func(console, msg)
#   on_recv => func(console, msg)
class Console(object):

    #---------------------------------------------------------------------------
    def __init__(self, serial_port, baud_rate=9600):
        self.logger = logging.getLogger('juliet.Console')
        self.logger.info('Starting console on %s', serial_port)

        self.comm = serial.Serial(serial_port, baud_rate, timeout=1)
        self.comm_lock = threading.Lock()

        self.run_workers = True

        # initialize transmitter event / thread / queue
        self.xmit_queue = queue.Queue()
        self.on_xmit = Event()
        self.transmitter = threading.Thread(target=self._xmit_worker, daemon=True)
        self.transmitter.start()

        # initialize receiver event / thread / queue
        self.on_recv = Event()
        self.receiver = threading.Thread(target=self._recv_worker, daemon=True)
        self.receiver.start()

    #---------------------------------------------------------------------------
    def send(self, msg):
        if msg is None or len(msg) == 0:
            return False

        self.logger.debug('queueing XMIT message -- %s', msg[:10])
        self.xmit_queue.put(msg)

        return True

    #---------------------------------------------------------------------------
    def close(self):
        self.logger.info('Stopping communication')
        self.run_workers = False

        self.logger.debug('waiting for transmitter...')
        self.transmitter.join()

        self.logger.debug('waiting for receiver...')
        self.receiver.join()

        self.logger.debug('all workers finished; closing port')
        self.comm.close()

    #---------------------------------------------------------------------------
    def _recv_worker(self):
        while self.run_workers:
            self.comm_lock.acquire()
            msg_data = self.comm.readline()
            self.comm_lock.release()

            if msg_data and len(msg_data) > 0:
                msg = str(msg_data, 'utf-8')
                self.logger.debug('received message -- %s', msg[:10])
                self.on_recv(self, msg)

            time.sleep(0)  ## yield to xmit thread

    #---------------------------------------------------------------------------
    def _xmit_worker(self):
        while self.run_workers:
            try:
                msg = self.xmit_queue.get(timeout=1)
                msg_data = bytes(msg, 'utf-8')

                with self.comm_lock:
                    self.comm.write(msg_data)

                self.logger.debug('transmitted message -- %s', msg[:10])
                self.on_xmit(self, msg)

            except queue.Empty:
                pass

            time.sleep(0)  ## yield to recv thread

################################################################################
def parse_args():
    import argparse

    argp = argparse.ArgumentParser(description='juliet: a simple 2-way serial text client')

    argp.add_argument('--config', default='juliet.cfg',
                      help='configuration file (default: juliet.cfg)')

    # juliet.cfg overrides these values
    argp.add_argument('--port', help='serial port for comms')
    argp.add_argument('--baud', help='baud rate for comms')

    return argp.parse_args()

################################################################################
def load_config(args):
    import yaml
    import logging.config

    try:
        from yaml import CLoader as YamlLoader
    except ImportError:
        from yaml import Loader as YamlLoader

    config_file = args.config

    if not os.path.exists(config_file):
        print(f'ERROR: config file does not exist: {config_file}')
        return None

    with open(config_file, 'r') as fp:
        conf = yaml.load(fp, Loader=YamlLoader)

        # determine if logging is already configured...
        root_logger = logging.getLogger()
        if not root_logger.hasHandlers():
            if 'logging' in conf:
                logging.config.dictConfig(conf['logging'])
            else:
                logging.basicConfig(level=logging.WARN)

    # TODO error checking on parameters

    if 'port' not in conf:
        conf['port'] = args.port

    if 'baud' not in conf:
        conf['baud'] = args.baud

    return conf

################################################################################
def main(console):
    while True:
        msg = input('> ')
        console.send(msg)

################################################################################
## MAIN ENTRY

# TODO consider using curses for an entry cell and history cell
# TODO support arrow keys for xmit history

if __name__ == '__main__':
    args = parse_args()
    conf = load_config(args)

    console = Console(
        serial_port=conf['port'],
        baud_rate=conf['baud']
    )

    try:
        main(console)
    except EOFError:
        pass

    console.close()

