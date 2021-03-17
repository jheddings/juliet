# juliet - an IRC bot for relaying to radio networks

import re
import queue
import threading
import socket
import time
import logging

from datetime import datetime, timezone

from .event import Event

SOCKET_BUFFER_SIZE = 1024

regex_eol = re.compile(rb'\r?\n')
regex_irc_message = re.compile(rb'^^(:(?P<prefix>[^:\s]+)\s+)?((?P<command>[a-zA-Z]+)|(?P<reply>[0-9]+))\s*(?P<params>.+)?$')

################################################################################
class Message(object):

    #---------------------------------------------------------------------------
    def __init__(self, command, prefix=None, params=None, remarks=None):
        if command is None:
            raise ValueError('invalid command')

        self.prefix = prefix
        self.params = params
        self.remarks = remarks

        try:
            self.reply = int(command)
            self.command = None
        except ValueError:
            self.command = command
            self.reply = None

    #---------------------------------------------------------------------------
    def parse(line):
        match = regex_irc_message.match(line)

        # XXX should we return None or raise?
        if match is None or match is False:
            return None

        # XXX we may need to handle reply's differently in the future...
        cmd = match.group('reply') or match.group('command')

        msg = Message(cmd.decode('utf-8').upper())

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

        if self.command is None:
            string += '{0:03n}'.format(self.reply)
        else:
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
class Client():

    #---------------------------------------------------------------------------
    def __init__(self, nick, name='Juliet Radio Bot'):
        self.logger = logging.getLogger('juliet.Client')

        self.nickname = nick
        self.fullname = name

        self.active = False
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
        self.on_disconnect = Event()

        self.on_join = Event()
        self.on_kill = Event()
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
        return (self.active and self.daemon is not None and self.socket is not None)

    #---------------------------------------------------------------------------
    def connect(self, server, port=6667, passwd=None):
        self.logger.debug('connecting to IRC server: %s:%d', server, port)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((server, port))

        if passwd is not None:
            self._send('PASS {0}', passwd)

        self._send('NICK {0}', self.nickname)
        self._send('USER {0} - {1}', self.nickname, self.fullname)

        # startup the daemon if configured...
        self.daemon.start()

        # notify on_connect event handlers
        self.on_connect(self)

        self.logger.info('Connected to IRC server -- %s:%d', server, port)

    #---------------------------------------------------------------------------
    def disconnect(self):
        self.logger.info('Closing server connection')

        if self.socket:
            self.quit()

        self.daemon.join()
        self.socket = None

        self.on_disconnect(self)

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

        self.socket = None

    #---------------------------------------------------------------------------
    def _on_ping(self, client, origin):
        client._send('PONG {0} :{1}', client.nickname, origin)

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

        if msg.reply == 1:
            self.logger.debug('received welcome -- %s', msg.remarks)
            self.on_welcome(self, msg.remarks)

        elif msg.command == 'PING':
            self.logger.debug('received PING -- %s', msg.remarks)
            self.on_ping(self, msg.remarks)

        elif msg.command == 'PRIVMSG':
            self.logger.debug('received PRIVMSG [%s] -- %s', msg.prefix, msg.remarks[:10])
            recip = msg.params[0]
            self.on_privmsg(self, msg.prefix, recip, msg.remarks)

        elif msg.command == 'NOTICE':
            self.logger.debug('received NOTICE [%s] -- %s', msg.prefix, msg.remarks[:10])
            recip = msg.params[0]
            self.on_notice(self, msg.prefix, recip, msg.remarks)

        elif msg.command == 'JOIN':
            channel = msg.params[0]
            self.logger.debug('JOIN channel %s', channel)
            self.on_join(self, channel)

        elif msg.command == 'PART':
            channel = msg.params[0]
            self.logger.debug('PART channel %s', channel)
            self.on_part(self, channel, msg.remarks)

        elif msg.command == 'KILL':
            self.logger.debug('killed by %s -- %s', msg.prefix, msg.remarks)
            self.on_kill(self, msg.prefix, msg.remarks)

    #---------------------------------------------------------------------------
    def _thread_worker(self):
        self.logger.debug(': begin comm loop')

        self.active = True

        while self.socket:
            data = None

            try:
                data = self.socket.recv(SOCKET_BUFFER_SIZE)

                if not data:
                    self.logger.debug('socket closed by remote')
                    break

            except socket.error as err:
                self.logger.debug('socket error', exc_info=True)
                break

            self.logger.debug('received data -- %s', data)
            self.last_contact = datetime.now(tz=timezone.utc)

            self.buffer += data
            self._parse_buffer()

        self.active = False

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

