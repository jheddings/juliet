##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import os
import sys

from . import config
from . import irc
from . import radio

from juliet import Juliet

################################################################################
## MAIN ENTRY

conf = config.UserConfig()

radio = radio.RadioComm(
    serial_port=conf.radio_port,
    baud_rate=conf.radio_baud
)

jules = Juliet(
    nick=conf.irc_server_nick,
    realname=conf.irc_server_realname,
    server=conf.irc_server_host,
    port=conf.irc_server_port,
    channels=conf.irc_channels,
    radio=radio
)

try:
    jules.start()
except KeyboardInterrupt:
    jules.disconnect('offline')

radio.close()

