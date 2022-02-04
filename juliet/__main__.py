##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import logging

from juliet import Juliet

from . import config, radio
from .version import __version__

__all__ = ["__version__"]

## MAIN ENTRY

conf = config.UserConfig()
log = logging.getLogger(__name__)

radio = radio.RadioComm(serial_port=conf.radio_port, baud_rate=conf.radio_baud)

jules = Juliet(
    nick=conf.irc_server_nick,
    realname=conf.irc_server_realname,
    server=conf.irc_server_host,
    port=conf.irc_server_port,
    channels=conf.irc_channels,
    radio=radio,
)

try:
    jules.start()
except KeyboardInterrupt:
    log.info("Canceled by user")
    jules.disconnect("offline")

radio.close()
