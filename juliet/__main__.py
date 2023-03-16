##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import logging

from juliet import Juliet

from . import config, radio

## MAIN ENTRY

conf = config.User()
log = logging.getLogger(__name__)

radio = radio.RadioComm(
    serial_port=conf.RADIO_COMM_PORT, baud_rate=conf.RADIO_BAUD_RATE
)

jules = Juliet(
    nick=conf.IRC_NICKNAME,
    realname=conf.IRC_REALNAME,
    server=conf.IRC_SERVER_HOST,
    port=conf.IRC_SERVER_PORT,
    channels=conf.IRC_CHANNELS,
    radio=radio,
)

try:
    jules.start()
except KeyboardInterrupt:
    log.info("Canceled by user")
    jules.disconnect("offline")

radio.close()
