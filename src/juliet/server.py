import socket
import threading
import re
import time
import logging
import juliet

from datetime import datetime, timezone

SOCKET_BUFFER_SIZE = 1024
SESSION_TIMEOUT_SEC = 300

regex_eol = re.compile(rb'\r?\n')
regex_nickname = re.compile(rb'[a-zA-Z0-9|`\\_{}\[\]-]+')

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
        self.fullname = None

        self.pending_welcome = None
        self.authorized = (server.password is None)
        self.host, self.port = socket.getpeername()
        self.logger = logging.getLogger('juliet.Session')
        self.send_lock = threading.Lock()

        # create event handlers
        self.on_away = juliet.Event()
        self.on_motd = juliet.Event()
        self.on_nick = juliet.Event()
        self.on_ping = juliet.Event()
        self.on_pong = juliet.Event()
        self.on_quit = juliet.Event()
        self.on_user = juliet.Event()

        # set up the worker thread for this session
        self.worker_thread = threading.Thread(
            name=f'session-{id(self)}', target=self._thread_worker, daemon=True
        )

        self.worker_thread.start()

    #---------------------------------------------------------------------------
    def close(self):
        self.logger.debug('closing session')

        if self.active and self.socket:
            try:
                self.socket.close()
            except socket.error:
                self.logger.debug('socket closed -- nothing to do')

        self.socket = None
        self.server.remove_session(self.nickname)

    #---------------------------------------------------------------------------
    def handle_user(self, args):
        parts = args.split(b':', 1)
        user_info = parts[0].split()

        self.logger.debug('welcome user %s', user_info)
        self.username = user_info[0].decode('utf-8')
        self.fullname = None if len(parts) < 2 else parts[1].decode('utf-8')

        if self.nickname is None:
            self.pending_welcome = True
        else:
            self.send_welcome()

        self.on_user(self, self.username)

    #---------------------------------------------------------------------------
    def handle_nick(self, nick):
        if nick is None:
            self.notify('431 :Missing nickname')

        elif self.server.get_session(nick):
            self.notify('433 * %s :Nickname in use', nick)

        elif not regex_nickname.match(nick):
            self.notify('432 * %s :Invalid nickname', nick)

        else:
            self.nickname = nick.decode('utf-8')
            self.logger.info('registered nickname -- %s', self.nickname)

            if self.pending_welcome:
                self.send_welcome()

            self.on_nick(self, self.nickname)

    #---------------------------------------------------------------------------
    def handle_away(self, away):
        if away:
            self.away = away.decode('utf-8')
            self.logger.info('@%s is away -- %s', self.nickname, away)
        else:
            self.away = False
            self.logger.info('@%s is not away', self.nickname)

        self.on_away(self, away)

    #---------------------------------------------------------------------------
    def handle_motd(self):
        if self.server.motd is None:
            self.notify('422 {} :MOTD is missing', self.nickname)
        else:
            self.notify('375 {} :- {} Message of the day -', self.nickname, self.server.name)
            self.notify('372 {} :- {}', self.nickname, self.server.motd.strip())
            self.notify('376 {} :End of MOTD command', self.nickname)

        self.on_motd(self, self.server.motd)

    #---------------------------------------------------------------------------
    def handle_ping(self, args):
        if args is None:
            self.notify('409 {} :Missing origin', self.nickname)
        else:
            token = args.decode('utf-8')
            self.notify('PONG {} :{}', self.server.name, token)
            self.on_ping(self, token)

    #---------------------------------------------------------------------------
    def handle_pong(self, args):
        if args is None:
            self.notify('409 {} :Missing origin', self.nickname)
        else:
            token = args.decode('utf-8')
            self.on_pong(self, token)

    #---------------------------------------------------------------------------
    def handle_quit(self, reason):
        if reason is not None:
            reason = reason.decode('utf-8')

        self.logger.info('User quit -- %s%s', self.nickname, reason or '')

        self.close()

        self.on_quit(self, reason)

    #---------------------------------------------------------------------------
    def handle_command(self, command, args):
        if command is None: return

        # TODO if server has password, check session authorized before other commands

        command = command.upper()
        self.logger.debug('command -- %s [%s]', command, args)

        if command == 'AWAY':
            self.handle_away(args)
        elif command == 'CAP':
            pass
        elif command == 'MODE':
            pass
        elif command == 'MOTD':
            self.handle_motd()
        elif command == 'NICK':
            self.handle_nick(args)
        elif command == 'PASS':
            pass
        elif command == 'PING':
            self.handle_ping(args)
        elif command == 'PONG':
            self.handle_pong(args)
        elif command == 'QUIT':
            self.handle_quit(args)
        elif command == 'USER':
            self.handle_user(args)
        else:
            self.logger.warning('Unrecognized command -- %s', command)

    #---------------------------------------------------------------------------
    def parse_buffer(self):
        lines = regex_eol.split(self.buffer)
        self.buffer = b''

        for line in lines:
            if not line: continue

            parts = line.split(b' ', 1)
            command = parts[0].decode('utf-8', errors='replace')
            args = None if len(parts) == 1 else parts[1]

            try:
                self.handle_command(command, args)
            except:
                self.logger.error('error processing command', exc_info=True)

    #---------------------------------------------------------------------------
    def send(self, msg, *args):
        if args is not None:
            msg = msg.format(*args)

        resp = f'{msg}\r\n'

        with self.send_lock:
            self.logger.debug('>> %s', msg)
            self.socket.send(bytes(resp, 'utf-8'))

    #---------------------------------------------------------------------------
    def send_ping(self):
        self.send('PING {}', self.server.hostname)

    #---------------------------------------------------------------------------
    def notify(self, msg, *args):
        if args is not None:
            msg = msg.format(*args)

        self.send(':{} {}', self.server.name, msg)

    #---------------------------------------------------------------------------
    def send_welcome(self):
        self.logger.info('Registering new user -- %s @%s', self.username, self.nickname)

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

        self.handle_motd()

        self.pending_welcome = False

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
        self.session_lock = threading.Lock()

        self.active = None
        self.start_time = datetime.now(tz=timezone.utc)

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
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        ping_thread = threading.Thread(
            name=f'SessionPing', target=self._ping_worker, daemon=True
        )

        self.active = True

        with self.socket:
            self.socket.bind((self.address, self.port))
            self.socket.listen()
            self.logger.info('Server started -- %s:%d', self.address, self.port)

            ping_thread.start()

            while self.active:
                conn, addr = self.socket.accept()
                self.logger.info('Client connected -- %s:%d', addr[0], addr[1])

                session = Session(self, conn)
                with self.session_lock:
                    self.sessions.append(session)

        ping_thread.join()
        self.logger.info('Server stopped')

    #---------------------------------------------------------------------------
    def stop(self):
        self.logger.debug('stopping server')
        self.active = False

        # TODO close sessions gracefully

        for session in self.sessions:
            session.close()

        self.sessions = list()
        self.socket.close()

    #---------------------------------------------------------------------------
    def remove_session(self, nick):
        self.logger.debug('removing session -- %s', nick)

        session = self.get_session(nick)

        if session is None:
            self.logger.warning('Invalid session; nickname not found: %s', nick)
        else:
            with self.session_lock:
                self.sessions.remove(session)

    #---------------------------------------------------------------------------
    def get_session(self, nick):
        self.logger.debug('looking for session -- %s', nick)

        with self.session_lock:
            for session in self.sessions:
                if session.nickname == nick:
                    return session

        return None

    #---------------------------------------------------------------------------
    def _ping_worker(self):
        self.logger.debug('ping thread starting')

        while self.active:
            with self.session_lock:
                now = datetime.now(tz=timezone.utc)
                self.logger.debug('checking active sessions -- %s', now)

                for session in self.sessions:
                    last_contact = now - session.last_contact
                    total_sec = last_contact.total_seconds()

                    self.logger.debug('session [%s] last contact: %s sec', id(session), last_contact)

                    if total_sec > SESSION_TIMEOUT_SEC * 1.25:
                        self.logger.debug('client timeout')
                        session.close()
                    elif total_sec > SESSION_TIMEOUT_SEC:
                        self.logger.debug('client inactive')
                        session.send_ping()

            time.sleep(SESSION_TIMEOUT_SEC / 2)

        self.logger.debug('ping thread finished')

