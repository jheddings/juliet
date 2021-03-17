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
    def __init__(self):
        self.clients = list()
        self.active = False
        self.logger = logging.getLogger('juliet.Juliet')

    #---------------------------------------------------------------------------
    def attach(self, client):
        if client in self.clients:
            raise ValueError('duplicate client')

        client.on_connect += self._on_client_connect
        client.on_disconnect += self._on_client_disconnect
        client.on_privmsg += self._on_client_privmsg

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
    def _on_client_privmsg(self, client, sender, recip, txt):
        self.logger.debug('incoming message %s -> %s -- %s', sender, recip, txt)

        # TODO if we get a direct message, process the command
        if recip == client.nickname:
            self.logger.debug('handle command -- %s', txt)

        # TODO if we get a channel message, broadcast to radio
        else:
            self.logger.debug('transmit message -- %s', txt)

    #---------------------------------------------------------------------------
    def _on_client_connect(self, client):
        self.clients.append(client)

    #---------------------------------------------------------------------------
    def _on_client_disconnect(self, client):
        self.clients.remove(client)

