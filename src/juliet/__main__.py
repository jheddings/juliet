##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import os
import sys
import threading
import logging

from irc import server

from . import config
from . import radio

from juliet import Juliet

################################################################################
class IRCServerBroker(object):

    def __init__(self, conf):
        self.host = conf.irc_server_host
        self.port = conf.irc_server_port
        self.server = None

        self.logger = logging.getLogger('juliet.IRCServerBroker')

    def start(self):
        if self.host is not None:
            self.logger.debug('using remote IRC server -- %s:%d', self.host, self.port)
            return

        self.logger.debug('starting local IRC server on port %d', self.port)
        self.server = server.IRCServer(('0.0.0.0', self.port), server.IRCClient)
        self.host, self.port = self.server.server_address

        self.daemon = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.daemon.start()

    def stop(self):
        if self.server is None:
            self.logger.debug('server not running; nothing to do')
            return

        self.logger.debug('stopping local IRC server')
        self.server.shutdown()
        self.daemon.join()

        self.server = None
        self.daemon = None
        self.host = None

################################################################################
## MAIN ENTRY

conf = config.UserConfig()
logger = logging.getLogger('juliet.main')

radio = radio.RadioComm(
    serial_port=conf.radio_port,
    baud_rate=conf.radio_baud
)

broker = IRCServerBroker(conf)
broker.start()

jules = Juliet(
    nick=conf.irc_server_nick,
    realname=conf.irc_server_realname,
    server=broker.host,
    port=broker.port,
    channels=conf.irc_channels,
    radio=radio
)

# !! main applicaton start

try:
    jules.start()
except KeyboardInterrupt:
    logger.info('Canceled by user')
    jules.disconnect('offline')

# !! main applicaton exit

radio.close()
broker.stop()

