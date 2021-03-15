import socket
import threading
import re
import logging
import juliet

from datetime import datetime, timezone

SOCKET_BUFFER_SIZE = 1024

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

        host, port = socket.getpeername()
        self.hostname = host
        self.hostport = port

        self.registration_pending = None

        self.logger = logging.getLogger('juliet.Session')

        # create event handlers
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
            self.registration_pending = True
        else:
            self.process_registration()

        self.on_user(self, self.username)

    #---------------------------------------------------------------------------
    def handle_nick(self, nick):
        if nick is None:
            self.notice('431 :Missing nickname')

        elif self.server.get_session(nick):
            self.notice('433 * %s :Nickname in use', nick)

        elif not regex_nickname.match(nick):
            self.notice('432 * %s :Invalid nickname', nick)

        else:
            self.nickname = nick.decode('utf-8')
            self.logger.info('registered nickname -- %s', self.nickname)

            if self.registration_pending:
                self.process_registration()

            self.on_nick(self, self.nickname)

    #---------------------------------------------------------------------------
    def handle_away(self, away):
        self.away = away

        if away:
            away = away.decode('utf-8')
            self.logger.info('@%s is away -- %s', self.nickname, away)
        else:
            self.logger.info('@%s is not away', self.nickname)

    #---------------------------------------------------------------------------
    def handle_motd(self):
        if self.server.motd is None:
            self.notice('422 {} :MOTD is missing', self.nickname)
        else:
            self.notice('375 {} :- {} Message of the day -', self.nickname, self.server.name)
            self.notice('372 {} :- {}', self.nickname, self.server.motd.strip())
            self.notice('376 {} :End of MOTD command', self.nickname)

        self.on_motd(self, self.server.motd)

    #---------------------------------------------------------------------------
    def handle_ping(self, args):
        if args is None:
            self.notice('409 {} :Missing origin', self.nickname)
        else:
            token = args.decode('utf-8')
            self.notice('PONG {} :{}', self.server.name, token)
            self.on_ping(self, token)

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
    def notice(self, msg, *args):
        if args is not None:
            msg = msg.format(*args)

        string = f':{self.server.name} {msg}\r\n'

        self.logger.debug('>> %s', msg)
        self.socket.send(bytes(string, 'utf-8'))

    #---------------------------------------------------------------------------
    def process_registration(self):
        self.logger.info('Registering new user -- %s @%s', self.username, self.nickname)

        self.notice(
            '001 {} :Welcome to the mesh IRC network {} -- {}@{}',
            self.nickname, self.nickname, self.username, self.hostname
        )

        self.notice(
            '002 {} :Your host is {}, running juliet-{}',
            self.nickname, self.server.name, juliet.VERSION
        )

        self.notice(
            '003 {} :This server was created {}',
            self.nickname, self.server.start_time
        )

        self.notice(
            '004 {} {} juliet-{} o o',
            self.nickname, self.server.name, juliet.VERSION
        )

        #self.send_lusers()
        self.handle_motd()

        self.registration_pending = False

    #---------------------------------------------------------------------------
    def _thread_worker(self):
        self.logger.debug('starting new session')
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
    def __init__(self, address='', port=6667, motd=None, server_name=None):
        self.address = address
        self.port = port
        self.motd = motd

        self.socket = None
        self.sessions = list()

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

        with self.socket:
            self.socket.bind((self.address, self.port))
            self.socket.listen()
            self.logger.info('Server started -- %s:%d', self.address, self.port)

            while True:
                conn, addr = self.socket.accept()
                self.logger.info('Client connected -- %s:%d', addr[0], addr[1])

                session = Session(self, conn)
                self.sessions.append(session)

        self.logger.info('Server stopped')

    #---------------------------------------------------------------------------
    def stop(self):
        self.logger.debug('stopping server')

        # TODO close sessions gracefully

        for session in self.sessions:
            session.close()

        self.sessions = list()
        self.socket.close()

    #---------------------------------------------------------------------------
    def send(self, msg):
        self.logger.debug('stopping server')
        self.socket.sendall(msg)

    #---------------------------------------------------------------------------
    def remove_session(self, nick):
        session = self.get_session(nick)

        if session is None:
            self.logger.warning('Invalid session; nickname not found: %s', nick)
        else:
            self.sessions.remove(session)

    #---------------------------------------------------------------------------
    def get_session(self, nick):
        for session in self.sessions:
            if session.nickname == nick:
                return session

        return None

