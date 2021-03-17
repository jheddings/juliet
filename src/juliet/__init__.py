##
# juliet - an IRC relay bot for radio networks
##

VERSION = '0.0.1'

import time
import logging

from datetime import datetime, timezone

from .event import Event

SESSION_TIMEOUT_SEC = 90

################################################################################
class Juliet(object):

    #---------------------------------------------------------------------------
    def __init__(self, comm):
        self.clients = list()
        self.active = False
        self.comm = comm
        self.logger = logging.getLogger('juliet.Juliet')

        if comm is None:
            raise ValueError('comm not specified')

        comm.on_recv += self._comm_recv
        comm.on_xmit += self._comm_xmit

    #---------------------------------------------------------------------------
    def attach(self, client):
        if client in self.clients:
            raise ValueError('duplicate client')

        client.on_connect += self._client_connect
        client.on_disconnect += self._client_disconnect
        client.on_privmsg += self._client_privmsg

        self.logger.debug('client [%s] attached', id(client))

    #---------------------------------------------------------------------------
    def detach(self, client):
        if client not in self.clients:
            raise ValueError('no such client')

        client.disconnect()

        self.logger.debug('client [%s] detached', id(client))

    #---------------------------------------------------------------------------
    def start(self):
        self.logger.debug('starting main loop')
        self.active = True

        try:
            self._run()
        except KeyboardInterrupt:
            self.logger.info('Canceled by user')

        # clean up remaining clients...
        for client in self.clients:
            self.detach(client)

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
                    'client [%s] last contact: %s',
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
    def _client_privmsg(self, client, sender, recip, txt):
        self.logger.debug('incoming message %s -> %s -- %s', sender, recip, txt)

        # if we get a direct message, process the command
        if recip == client.nickname:
            parts = txt.split(' ', 1)
            params = None if len(parts) < 2 else parts[1].split()

            self._do_command(client, sender, parts[0], params)

        # TODO if we get a channel message, broadcast to radio
        else:
            self.logger.debug('transmit message -- %s', txt)

    #---------------------------------------------------------------------------
    def _client_connect(self, client):
        self.clients.append(client)

    #---------------------------------------------------------------------------
    def _client_disconnect(self, client):
        self.clients.remove(client)

    #---------------------------------------------------------------------------
    def _comm_recv(self, comm, data):
        self.logger.debug('[comm] << %s', data)

    #---------------------------------------------------------------------------
    def _comm_xmit(self, comm, data):
        self.logger.debug('[comm] >> %s', data)

    #---------------------------------------------------------------------------
    def _do_command(self, session, sender, cmd, params):
        self.logger.debug('handle command -- %s', cmd)

        if cmd == 'ping':
            session.privmsg(sender, 'pong')

        elif cmd == 'join':
            channel = params[0]
            session.join(channel)

        elif cmd == 'part':
            channel = params[0]
            session.part(channel)

        #TODO figure out which commands we want to support
        #elif cmd == 'quit':

