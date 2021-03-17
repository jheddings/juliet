#!/usr/bin/env python3

# juliet - an IRC bot for relaying to radio networks

import os
import sys
import re
import queue
import threading
import socket
import time
import logging
import serial

from datetime import datetime, timezone

SOCKET_BUFFER_SIZE = 1024
SESSION_TIMEOUT_SEC = 90

packed_msg_re = re.compile(r'^>>(?P<ver>[a-fA-F0-9]+):(?P<crc>[a-zA-Z0-9]+):(?P<sender>[a-zA-Z0-9~/=+_$@#*&%!|-]+)?:(?P<time>[0-9]{14})?:(?P<msg>.+)(?!\\):(?P<sig>[a-zA-Z0-9]+)?<<$')

regex_eol = re.compile(rb'\r?\n')
regex_irc_message = re.compile(rb'^(:(?P<prefix>[^:\s]+)\s+)?(?P<command>([a-zA-Z]+|[0-9]+))\s*(?P<params>.+)?$')

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
# modified from https://stackoverflow.com/a/2022629/197772
class Event(list):

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
class Message(object):

    #---------------------------------------------------------------------------
    def __init__(self, command, prefix=None, params=None, remarks=None):
        if command is None:
            raise ValueError('invalid command')

        self.prefix = prefix
        self.command = command
        self.params = params
        self.remarks = remarks

    #---------------------------------------------------------------------------
    def parse(line):
        match = regex_irc_message.match(line)

        # XXX should we return None or raise?
        if match is None or match is False:
            return None

        msg = Message(match.group('command').decode('utf-8').upper())

        if match.group('prefix') is not None:
            msg.prefix = match.group('prefix').decode('utf-8')

        if match.group('params') is not None:
            full_params = match.group('params').decode('utf-8')
            parts = full_params.split(':', 1)

            msg.params = parts[0].split()
            msg.remarks = None if len(parts) == 1 else parts[1]

        return msg

    #---------------------------------------------------------------------------
    def __repr__(self):
        string = ''

        if self.prefix:
            string += ':' + self.prefix + ' '

        string += self.command

        if self.params:
            for param in self.params:
                string += ' ' + param

        if self.remarks:
            string += ' :' + self.remarks

        return string

################################################################################
# a simple event-based IRC client
# modified from: https://github.com/jheddings/idlebot
#
# Events => Handler Function
#   on_welcome => func(client, msg)
#   on_connect => func(client)
#   on_quit => func(client, msg)
#   on_ping => func(client, txt)
#   on_privmsg => func(client, sender, recip, msg)
#   on_notice => func(client, sender, recip, msg)
#   on_join => func(client, channel)
#   on_part => func(client, channel, msg)
class Client():

    #---------------------------------------------------------------------------
    def __init__(self, nick, name='Juliet Radio Bot'):
        self.logger = logging.getLogger('juliet.Client')

        self.nickname = nick
        self.fullname = name

        self.buffer = b''
        self.last_contact = None

        self.daemon = threading.Thread(
            name='Juliet.Daemon',
            target=self._thread_worker,
            daemon=True
        )

        # initialize event handlers
        self.on_connect = Event()
        self.on_welcome = Event()

        self.on_join = Event()
        self.on_notice = Event()
        self.on_part = Event()
        self.on_ping = Event()
        self.on_privmsg = Event()
        self.on_quit = Event()

        # self-register for events we care about
        self.on_ping += self._on_ping

    #---------------------------------------------------------------------------
    @property
    def is_active(self):
        return (self.daemon is not None and self.socket is not None)

    #---------------------------------------------------------------------------
    def connect(self, server, port=6667, passwd=None):
        self.logger.debug('connecting to IRC server: %s:%d', server, port)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((server, port))

        # startup the daemon if configured...
        self.daemon.start()

        if passwd is not None:
            self._send('PASS {0}', passwd)

        self._send('NICK {0}', self.nickname)
        self._send('USER {0} - {1}', self.nickname, self.fullname)

        # notify on_connect event handlers
        self.on_connect(self)

    #---------------------------------------------------------------------------
    def join(self, channel):
        self._send('JOIN {0}', channel)

    #---------------------------------------------------------------------------
    def part(self, channel, msg):
        self._send('PART {0} :{1}', channel, msg)

    #---------------------------------------------------------------------------
    def ping(self):
        self._send('PING {0}', id(self))

    #---------------------------------------------------------------------------
    def privmsg(self, recip, msg):
        self._send('PRIVMSG {0} :{1}', recip, msg)

    #---------------------------------------------------------------------------
    def mode(self, nick, flags):
        self._send('MODE {0} {1}', nick, flags)

    #---------------------------------------------------------------------------
    def quit(self, msg=None):
        if msg is None:
            self._send('QUIT')
        else:
            self._send('QUIT :{0}', msg)

        # wait for the deamon to exit...
        if (self.daemon is not None):
            self.daemon.join()

        # notify on_quit event handlers
        self.on_quit(self, msg)

        self.socket.close()
        self.logger.debug('connection closed')

    #---------------------------------------------------------------------------
    def _on_ping(self, client, origin):
        client._send('PONG {} :{0}', client.nickname, origin)

    #---------------------------------------------------------------------------
    def _send(self, msg, *args):
        if args is not None:
            msg = msg.format(*args)

        self.logger.debug('>> %s', msg)

        data = bytes(msg, 'utf-8') + b'\r\n'
        self.socket.sendall(data)

    #---------------------------------------------------------------------------
    def _handle_message(self, msg):
        self.logger.debug('incoming message -- %s', msg)

        if msg.command == '001':
            self.on_welcome(self, msg.remarks)

        elif msg.command == 'PING':
            self.on_ping(self, msg.remarks)

        elif msg.command == 'PRIVMSG':
            self.on_privmsg(self, origin, recip, txt)

        elif msg.command == 'NOTICE':
            self.on_notice(self, origin, recip, txt)

        elif msg.command == 'JOIN':
            self.on_join(self, channel)

        elif msg.command == 'PART':
            self.on_part(self, channel, txt)

    #---------------------------------------------------------------------------
    def _thread_worker(self):
        self.logger.debug(': begin comm loop')

        while self.socket:
            data = None

            try:
                data = self.socket.recv(SOCKET_BUFFER_SIZE)

                if not data:
                    self.logger.debug('socket close by remote')
                    break

            except socket.error as err:
                self.logger.debug('socket error', exc_info=True)
                break

            self.logger.debug('received data -- %s', data)
            self.last_contact = datetime.now(tz=timezone.utc)

            self.buffer += data
            self._parse_buffer()

    #---------------------------------------------------------------------------
    def _parse_buffer(self):
        lines = regex_eol.split(self.buffer)

        # split will leave an empty element if the end of the buffer is a newline
        # otherwise, it will contain a partial command that is picked up next time
        self.buffer = lines[-1]

        for line in lines:
            # skip empty lines...
            if not line: continue

            self.logger.debug('<< %s', line)
            msg = Message.parse(line)

            if not msg:
                self.logger.warning('invalid message -- %s', line)
                continue

            try:
                self._handle_message(msg)
            except:
                self.logger.error('error processing command', exc_info=True)

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
    def send(self, data): raise NotImplemented()

    #---------------------------------------------------------------------------
    def close(self): raise NotImplemented()

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

    #---------------------------------------------------------------------------
    def close(self):
        pass

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

################################################################################
class Juliet(object):

    #---------------------------------------------------------------------------
    def __init__(self):
        self.clients = list()
        self.logger = logging.getLogger('juliet.Juliet')

    #---------------------------------------------------------------------------
    def attach(self, client):
        if client in self.clients:
            raise ValueError('duplicate client')

        client.on_quit += self._on_client_quit
        self.clients.append(client)

    #---------------------------------------------------------------------------
    def detach(self, client):
        if client not in self.clients:
            raise ValueError('no such client')

        self.clients.remove(client)

    #---------------------------------------------------------------------------
    def start(self):
        self.logger.debug('starting main loop')
        self.active = True

        try:
            self._run()
        except KeyboardInterrupt:
            self.logger.info('Canceled by user')

        self.active = False
        self.logger.debug('exiting main loop')

    #---------------------------------------------------------------------------
    def stop(self):
        self.logger.debug('stopping main loop')
        self.active = False

    #---------------------------------------------------------------------------
    def _run(self):
        while self.active:
            time.sleep(SESSION_TIMEOUT_SEC / 2)
            now = datetime.now(tz=timezone.utc)

            for client in self.clients:
                last_contact = now - client.last_contact
                total_sec = last_contact.total_seconds()

                self.logger.debug(
                    'client [%s] last contact: %s sec',
                    id(client), last_contact
                )

                if not client.is_active:
                    self.logger.debug('client inactive')
                    self.detach(client)

                elif total_sec > SESSION_TIMEOUT_SEC * 2:
                    self.logger.debug('client timeout')
                    self.detach(client)

                elif total_sec > SESSION_TIMEOUT_SEC:
                    self.logger.debug('client idle')
                    client.ping()

    #---------------------------------------------------------------------------
    def _on_client_quit(self, client, reason):
        self.detach(client)

################################################################################
def load_config(config_file):
    import yaml
    import logging.config

    try:
        from yaml import CLoader as YamlLoader
    except ImportError:
        from yaml import Loader as YamlLoader

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

    return conf

################################################################################
## MAIN ENTRY

if __name__ == '__main__':
    config_file = sys.argv[1]
    conf = load_config(config_file)

    jules = Juliet()

    client = Client(nick='juliet')
    jules.attach(client)

    client.connect('defiant.local')

    jules.start()

    client.quit()

