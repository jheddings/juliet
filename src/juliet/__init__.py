##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

VERSION = '0.0.1'

import time
import logging
import irc.bot

from datetime import datetime, timezone

from .event import Event
from .message import TextMessage, ChannelMessage

################################################################################
class Juliet(irc.bot.SingleServerIRCBot):

    #---------------------------------------------------------------------------
    def __init__(self, name, radio, server, port=6667):
        irc.bot.SingleServerIRCBot.__init__(self, [(server, port)], name, name)

        self.radio = radio
        self.logger = logging.getLogger('juliet.RadioBot')

        if radio is None:
            raise ValueError('radio not specified')

        radio.on_recv += self._radio_recv
        radio.on_xmit += self._radio_xmit

    #---------------------------------------------------------------------------
    def on_nicknameinuse(self, conn, event):
        conn.nick(conn.get_nickname() + "_")

    #---------------------------------------------------------------------------
    def on_welcome(self, conn, event):
        self.logger.info('Juliet online: [%s]', conn.get_nickname())

        # TODO join default channels
        #conn.join(self.channel)

    #---------------------------------------------------------------------------
    def on_privmsg(self, conn, event):
        self.logger.debug('incoming message %s -- %s', event.type, event.arguments)

        sender = event.source.nick
        parts = event.arguments[0].split()
        cmd = parts[0]
        params = parts[1:]

        # if we get a direct message, process the command
        if event.target == conn.get_nickname():
            self._do_command(conn, sender, cmd, params)

    #---------------------------------------------------------------------------
    def on_pubmsg(self, conn, event):
        self.logger.debug('transfer message %s -- %s', event.target, event.arguments)

        text = event.arguments[0]
        channel = event.target
        sender = self.radio.station.name

        msg = ChannelMessage(content=text, channel=channel, sender=sender)

        data = msg.pack()
        self.radio.send(data)

    #---------------------------------------------------------------------------
    def _radio_recv(self, radio, data):
        self.logger.debug('[radio] << %s', data)

    #---------------------------------------------------------------------------
    def _radio_xmit(self, radio, data):
        self.logger.debug('[radio] >> %s', data)

    #---------------------------------------------------------------------------
    def _do_command(self, conn, sender, cmd, params):
        self.logger.debug('handle command [%s] -- %s %s', sender, cmd, params)

        if cmd == 'ping':
            if len(params) > 0:
                conn.privmsg(sender, f'pong {" ".join(params)}')
            else:
                conn.privmsg(sender, f'pong')

        elif cmd == 'join':
            channel = params[0]
            conn.privmsg(sender, f'On my way to {channel}')
            conn.join(channel)

        elif cmd == 'part':
            channel = params[0]
            conn.privmsg(sender, f'Leaving {channel}')
            conn.part(channel)

        elif cmd == 'xmit':
            text = ' '.join(params)
            sender = self.radio.station.name
            msg = TextMessage(content=text, sender=sender)
            data = msg.pack()
            self.radio.send(data)
            conn.privmsg(sender, 'Your message has been sent!')

        else:
            conn.notice(sender, f'Sorry, I don\'t understand "{cmd}"')

