import socket
import threading
import re
import time
import logging
import juliet

from datetime import datetime, timezone

SOCKET_BUFFER_SIZE = 1024
SESSION_TIMEOUT_SEC = 90

# used for message parsing (bytes)...
regex_eol = re.compile(rb'\r?\n')
regex_message = re.compile(rb'^(:(?P<prefix>[\w]+))?\s*(?P<command>\w+)\s*(?P<params>.+)?$')

# used for handling params (str)...
regex_nickname = re.compile(r'^[a-zA-Z0-9|`\\_{}\[\]-]{1,16}$')
regex_channel = re.compile(r'^[#&][^ ,]{1,200}')

# TODO review events to look for possible refactoring opportunity

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
    def parse(message):
        match = regex_message.match(message)

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
            string += ':' + self.prefix

        string += self.command

        if self.params:
            for param in self.params:
                string += ' ' + param

        if self.remarks:
            string += ' :' + self.remarks

        return string

################################################################################
class Channel(object):

    #---------------------------------------------------------------------------
    def __init__(self, name, topic=None, key=None):
        self.name = name
        self.key = key
        self.topic = topic
        self.members = list()
        self.members_lock = threading.Lock()
        self.logger = logging.getLogger('juliet.Channel')

    #---------------------------------------------------------------------------
    def add_member(self, session):
        if session not in self.members:
            with self.members_lock:
                self.members.append(session)

        self.logger.info('User [%s] joined channel %s', session.nickname, self.name)

    #---------------------------------------------------------------------------
    def remove_member(self, session):
        if session not in self.members:
            raise AttributeError('session not in channel')

        with self.members_lock:
            self.members.remove(session)

        self.logger.info('User [%s] left channel %s', session.nickname, self.name)

    #---------------------------------------------------------------------------
    def notify(self, sender, message, include_sender=False):
        msg = f':{sender.prefix} {message}'
        self.logger.debug('channel message -- %s', msg)

        with self.members_lock:
            for session in self.members:
                if session != sender or include_sender:
                    session.send(msg)

################################################################################
class Session(object):

    #---------------------------------------------------------------------------
    def __init__(self, server, socket):
        self.server = server
        self.socket = socket

        self.last_contact = None
        self.buffer = b''
        self.away = None

        self.nickname = None
        self.username = None
        self.full_name = None
        self.channels = dict()

        self.host, self.port = socket.getpeername()
        self.pending_welcome = None
        self.authorized = (server.password is None)
        self.send_lock = threading.Lock()
        self.logger = logging.getLogger('juliet.Session')

        # create event handlers
        self.on_away = juliet.Event()
        self.on_join = juliet.Event()
        self.on_motd = juliet.Event()
        self.on_nick = juliet.Event()
        self.on_part = juliet.Event()
        self.on_ping = juliet.Event()
        self.on_pong = juliet.Event()
        self.on_quit = juliet.Event()
        self.on_user = juliet.Event()
        self.on_privmsg = juliet.Event()
        self.on_welcome = juliet.Event()

        # set up the worker thread for this session
        self.worker_thread = threading.Thread(
            name=f'session-{id(self)}', target=self._thread_worker, daemon=True
        )

        self.worker_thread.start()

    #---------------------------------------------------------------------------
    @property
    def prefix(self):
        return f'{self.nickname}!{self.username}@{self.host}'

    #---------------------------------------------------------------------------
    @property
    def is_active(self):
        return (self.active and self.socket)

    #---------------------------------------------------------------------------
    def close(self):
        self.logger.debug('closing session')

        for channel in self.channels.values():
            channel.remove_member(self)

        try:
            self.socket.close()
        except socket.error:
            self.logger.debug('socket closed -- nothing to do')

        self.socket = None

    #---------------------------------------------------------------------------
    def handle_user(self, msg):
        if msg.params is None or len(msg.params) < 3:
            self.notify('461 :Not enough parameters')
            return

        if self.username:
            self.notify('462 :Already registered')
            return

        # TODO check if the username exists

        self.username = msg.params[0]
        self.full_name = msg.remarks

        self.logger.debug('new user %s', self.username)

        if self.nickname is None:
            self.pending_welcome = True
        else:
            self.send_welcome()

        self.on_user(self, self.username)

    #---------------------------------------------------------------------------
    def handle_nick(self, msg):
        if msg.params is None:
            self.notify('431 :Missing nickname')
            return

        nick = msg.params[0]

        if self.server.get_session(nick):
            self.notify('433 * {} :Nickname in use', nick)
            return

        if not regex_nickname.match(nick):
            self.notify('432 * {} :Invalid nickname', nick)
            return

        self.nickname = nick
        self.logger.info('registered nickname -- %s', self.nickname)

        if self.pending_welcome:
            self.send_welcome()

        self.on_nick(self, self.nickname)

    #---------------------------------------------------------------------------
    def handle_away(self, msg):
        if msg.remarks is None:
            self.away = False
            self.logger.info('%s is not away', self.nickname)

        else:
            self.away = msg.remarks
            self.logger.info('%s is away -- %s', self.nickname, self.away)

        self.on_away(self, self.away)

    #---------------------------------------------------------------------------
    def handle_motd(self):
        motd = self.server.motd

        if motd is None:
            self.notify('422 {} :MOTD is missing', self.nickname)

        else:
            # TODO wrap at 80 chars...
            motd = motd.strip()

            self.notify('375 {} :- {} Message of the day -', self.nickname, self.server.name)
            self.notify('372 {} :- {}', self.nickname, motd)
            self.notify('376 {} :End of MOTD command', self.nickname)

        self.on_motd(self, motd)

    #---------------------------------------------------------------------------
    def handle_join(self, msg):
        if msg.params is None:
            self.notify('461 {} :Missing parameters', self.nickname)

        elif msg.params[0] == 0:
            self.logger.debug('%s is leaving all channels', self.nickname)

            for name in self.channels:
                self.part_channel(name)

        else:
            channels = msg.params[0].split(',')
            keys = list()

            if len(msg.params) >= 2:
                keys = msg.params[1].split(',')

            for idx in range(len(channels)):
                name = channels[idx]
                key = None if idx >= len(keys) else keys[idx]
                self.join_channel(name, key)

    #---------------------------------------------------------------------------
    def handle_part(self, msg):
        if msg.params is None:
            self.notify('461 {} :Missing parameters', self.nickname)

        else:
            for name in msg.params:
                self.part_channel(name)

    #---------------------------------------------------------------------------
    def handle_mode(self, msg):
        subject = None if len(msg.params) < 1 else msg.params[0]

        if subject is None:
            self.notify('461 {} :Missing parameters', self.nickname)

        elif subject == self.nickname:
            flags = None if len(msg.params) == 1 else msg.params[1]

            if flags is None:
                self.notify('221 {} +', self.nickname)
            else:
                self.logger.debug('set user mode: %s => %s', self.nickname, flags)
                self.notify('501 {} :Unknown MODE -- {}', self.nickname, flags)

        # FIXME channel name to lower case
        elif subject in self.channels:
            channel = self.channels[subject]
            flags = None if len(msg.params) == 1 else msg.params[1]

            if flags is None:
                self.notify('324 {} {} +', self.nickname, channel.name)
            else:
                self.logger.debug('set channel mode: %s => %s', channel.name, flags)
                self.notify('472 {} :Unknown MODE -- {}', self.nickname, flags)

        else:
            self.notify('442 {} :Not on channel -- {}', self.nickname, subject)
            #self.notify('403 {} {} :No such channel', self.nickname, subject)

    #---------------------------------------------------------------------------
    def handle_ping(self, msg):
        if msg.params is None:
            self.notify('409 {} :Missing origin', self.nickname)

        else:
            origin = msg.params[0]
            self.notify('PONG {} :{}', self.server.name, origin)
            self.on_ping(self, origin)

    #---------------------------------------------------------------------------
    def handle_pong(self, msg):
        if msg.params is None:
            self.notify('409 {} :Missing origin', self.nickname)

        else:
            origin = msg.params[0]
            self.on_pong(self, origin)

    #---------------------------------------------------------------------------
    def handle_privmsg(self, msg):
        if msg.params is None:
            self.notify('411 {} :No recipient', self.nickname)

        elif msg.remarks is None:
            self.notify('412 {} :No text to send', self.nickname)

        else:
            for recip in msg.params[0].split(','):
                self.privmsg(recip, msg.remarks)

    #---------------------------------------------------------------------------
    def handle_who(self, msg):
        if msg.params is None:
            pass
        else:
            subject = msg.params[0]
            channel = self.server.get_channel(subject)

            # XXX this is a bit of a hack, since we are directly accessing properties
            # of the server and channel objects...  might be okay, but keep an eye on it
            sessions = self.server.sessions if channel is None else channel.members

            for session in sessions:
                self.notify(
                    '352 {} {} {} {} {} {} H :0 {}',
                    self.nickname,
                    channel.name,
                    session.username,
                    session.host,
                    self.server.name,
                    session.nickname,
                    session.full_name
                )

            self.notify('315 {} {} :End of /WHO list', self.nickname, subject)

    #---------------------------------------------------------------------------
    def handle_quit(self, msg):
        self.logger.info('User quit -- %s:%s', self.nickname, msg.remarks)

        self.close()

        self.on_quit(self, msg.remarks)

    #---------------------------------------------------------------------------
    def handle_message(self, msg):
        if msg is None: return

        # TODO if server has password, check session authorized before other commands
        # TODO if user is not registered, block other commands

        self.logger.debug('incoming message -- %s', msg)

        if msg.command == 'AWAY':
            self.handle_away(msg)
        elif msg.command == 'JOIN':
            self.handle_join(msg)
        elif msg.command == 'LIST':
            pass
        elif msg.command == 'MODE':
            self.handle_mode(msg)
        elif msg.command == 'MOTD':
            self.handle_motd()
        elif msg.command == 'NICK':
            self.handle_nick(msg)
        elif msg.command == 'PART':
            self.handle_part(msg)
        elif msg.command == 'PASS':
            pass
        elif msg.command == 'PING':
            self.handle_ping(msg)
        elif msg.command == 'PONG':
            self.handle_pong(msg)
        elif msg.command == 'PRIVMSG':
            self.handle_privmsg(msg)
        elif msg.command == 'QUIT':
            self.handle_quit(msg)
        elif msg.command == 'USER':
            self.handle_user(msg)
        elif msg.command == 'WHO':
            self.handle_who(msg)
        else:
            self.notify('421 {} {} :Unknown command', self.nickname or '*', msg.command)

    #---------------------------------------------------------------------------
    def join_channel(self, name, key=None):
        if not regex_channel.match(name):
            self.notify('403 {} {} :No such channel', self.nickname, name)
            return

        channel = self.server.get_channel(name)
        if channel is None:
            channel = self.server.create_channel(name)

        if channel.key != key:
            self.notify(
                '475 {} {} :Wrong key for channel (+k)',
                self.nickname, channel.name
            )
            return

        channel.add_member(self)
        channel.notify(self, 'JOIN ' + channel.name, include_sender=True)
        # TODO send current users

        if channel.topic:
            self.notify('332 {} {} :{}', self.nickname, channel.name, channel.topic)
        else:
            self.notify('331 {} {} :No topic', self.nickname, channel.name)

        self.logger.info(
            '%s joined channel %s -- [key:%s]',
            self.nickname, channel.name, (key is not None)
        )

        self.channels[channel.name] = channel
        self.on_join(self, channel.name)

    #---------------------------------------------------------------------------
    def part_channel(self, name, remarks=None):
        self.logger.info('%s parted channel %s', self.nickname, name)

        channel = self.server.get_channel(name)

        if channel is None:
            self.notify('403 {} {} :No such channel', self.nickname, name)
        elif name not in self.channels:
            self.notify('442 {} :Not on channel -- {}', self.nickname, name)
        else:
            channel.notify(self, f'PART {name}', include_sender=True)
            channel.remove_member(self)
            self.channels.pop(channel.name, None)
            self.on_part(self, channel.name)

    #---------------------------------------------------------------------------
    def parse_buffer(self):
        lines = regex_eol.split(self.buffer)

        # split will leave an empty element if the end of the buffer is a newline
        # otherwise, it will contain a partial command that is picked up next time
        self.buffer = lines[-1]

        for line in lines:
            # skip empty lines...
            if not line: continue

            msg = Message.parse(line)

            if not msg:
                self.logger.warning('invalid message -- %s', line)
                continue

            try:
                self.handle_message(msg)
            except:
                self.logger.error('error processing command', exc_info=True)

    #---------------------------------------------------------------------------
    def send(self, msg):
        resp = f'{msg}\r\n'

        with self.send_lock:
            self.logger.debug('[%s] >> %s', id(self), msg)
            self.socket.send(bytes(resp, 'utf-8'))

    #---------------------------------------------------------------------------
    def notify(self, msg, *args):
        if args is not None:
            msg = msg.format(*args)

        self.send(f':{self.server.name} {msg}')

    #---------------------------------------------------------------------------
    def ping(self):
        try:
            self.send(f'PING {self.server.hostname}')
        except:
            pass

    #---------------------------------------------------------------------------
    def privmsg(self, recipient, message):
        self.logger.debug('privmsg %s -> %s -- %s', self.nickname, recipient, message)

        channel = self.server.get_channel(recipient)
        session = self.server.get_session(recipient)

        if session is not None:
            session.send(f'{self.prefix} PRIVMSG {recipient} {message}')
            self.on_privmsg(self, recipient, message)

        elif channel is not None:
            # use the real name of the channel...
            recipient = channel.name

            if recipient not in self.channels:
                self.notify('442 {} :Not on channel -- {}', self.nickname, recipient)
            else:
                channel.notify(self, f'PRIVMSG {recipient} :{message}')
                self.on_privmsg(self, recipient, message)

        else:
            self.notify('401 {} {} :No such recipient', self.nickname, recipient)

    #---------------------------------------------------------------------------
    def send_welcome(self):
        if self.username is None or self.nickname is None:
            raise AttributeError('incomplete user information')

        self.logger.info('User Registered -- %s %s', self.username, self.nickname)

        self.notify(
            '001 {} :Welcome to the mesh IRC network {} -- {}@{}',
            self.nickname, self.nickname, self.username, self.host
        )

        self.notify(
            '002 {} :Your host is {}, running juliet-{}',
            self.nickname, self.server.name, juliet.VERSION
        )

        self.notify(
            '003 {} :This server was created {}',
            self.nickname, self.server.start_time
        )

        self.notify(
            '004 {} {} juliet-{} o o',
            self.nickname, self.server.name, juliet.VERSION
        )

        self.notify(
            '251 {} :There are {} users on 1 server',
            self.nickname, len(self.server.sessions)
        )

        self.handle_motd()

        self.pending_welcome = False
        self.on_welcome(self)

    #---------------------------------------------------------------------------
    def _thread_worker(self):
        self.logger.debug('session [%s] started from %s:%d', id(self), self.host, self.port)

        self.active = True

        while self.active and self.socket:
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
            self.parse_buffer()

        self.active = False
        self.logger.debug('session closed')

################################################################################
class Server(object):

    #---------------------------------------------------------------------------
    def __init__(self, address='', port=6667, motd=None, password=None, server_name=None):
        self.address = address
        self.port = port
        self.motd = motd
        self.password = password
        self.socket = None

        self.sessions = list()
        self.session_lock = threading.RLock()

        self.channels = dict()

        self.active = None
        self.start_time = None

        server_name_limit = 63  # From the RFC.
        self.hostname = socket.getfqdn(address)[:server_name_limit]
        self.name = self.hostname if server_name is None else server_name

        self.logger = logging.getLogger('juliet.Server')

    #---------------------------------------------------------------------------
    def daemonize(self):
        pass

    #---------------------------------------------------------------------------
    def start(self):
        self.logger.debug('starting server -- %s:%d', self.address, self.port)

        self.start_time = datetime.now(tz=timezone.utc)

        watcher_thread = threading.Thread(
            name=f'SessionWatcher', target=self._watcher, daemon=True
        )

        self.active = True

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        with self.socket:
            self.socket.bind((self.address, self.port))
            self.socket.listen()
            self.logger.info('Server started -- %s:%d', self.address, self.port)

            watcher_thread.start()

            while self.active:
                conn, addr = self.socket.accept()
                self.logger.info('Client connected -- %s:%d', addr[0], addr[1])

                session = Session(self, conn)

                with self.session_lock:
                    self.sessions.append(session)

                session.on_quit += self.session_quit

        self.active = False

        watcher_thread.join()
        self.logger.info('Server stopped')

    #---------------------------------------------------------------------------
    def stop(self):
        self.logger.debug('stopping server')
        self.active = False

        with self.session_lock:
            for session in self.sessions:
                session.close()
                self.sessions.remove(session)

        self.socket.close()

    #---------------------------------------------------------------------------
    def session_quit(self, session, reason):
        self.logger.debug('session quit [%s] -- %s', id(session), reason)

        with self.session_lock:
            self.sessions.remove(session)

    #---------------------------------------------------------------------------
    def get_session(self, nick):
        self.logger.debug('looking for session -- %s', nick)

        with self.session_lock:
            session = next((s for s in self.sessions if s.nickname == nick), None)

        return session

    #---------------------------------------------------------------------------
    def get_channel(self, name):
        if name is None:
            raise ValueError('name cannot be None')

        return self.channels.get(name.lower(), None)

    #---------------------------------------------------------------------------
    def create_channel(self, name, key=None):
        if name is None:
            raise ValueError('name cannot be None')

        name = name.lower()

        if name in self.channels:
            raise AttributeError('channel exists')

        channel = Channel(name, key=key)
        self.channels[name] = channel

        self.logger.info('Channel %s created [key:%s]', name, (key is not None))

        return channel

    #---------------------------------------------------------------------------
    def _watcher(self):
        self.logger.debug('ping thread starting')

        while self.active:
            with self.session_lock:
                now = datetime.now(tz=timezone.utc)
                self.logger.debug('checking active sessions -- %s', now)

                for session in self.sessions:
                    last_contact = now - session.last_contact
                    total_sec = last_contact.total_seconds()

                    self.logger.debug('session [%s] last contact: %s sec', id(session), last_contact)

                    if not session.is_active:
                        self.logger.debug('client inactive')
                        self.session_quit(session, 'inactive')
                        session.close()

                    elif total_sec > SESSION_TIMEOUT_SEC * 2:
                        self.logger.debug('client timeout')
                        self.session_quit(session, 'timeout')
                        session.close()

                    elif total_sec > SESSION_TIMEOUT_SEC:
                        self.logger.debug('client idle')
                        session.ping()

            time.sleep(SESSION_TIMEOUT_SEC / 2)

        self.logger.debug('ping thread finished')

