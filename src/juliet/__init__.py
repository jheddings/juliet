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
from .message import MessageBuffer, Message, TextMessage, ChannelMessage

################################################################################
class Juliet(irc.bot.SingleServerIRCBot):

    #---------------------------------------------------------------------------
    def __init__(self, nick, radio, server, port=6667, realname=None, channels=None):
        super().__init__([(server, port)], nick, realname or nick)

        self.auto_channels = channels

        self.msgbuf = MessageBuffer()
        self.msgbuf.on_message += self._handle_message

        self.radio = radio
        self.logger = logging.getLogger('juliet.Juliet')

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

        if self.auto_channels:
            for channel in self.auto_channels:
                name = channel['name']
                key = channel['key'] if 'key' in channel else None
                conn.join(name, key)

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
        sender = event.source.nick

        msg = ChannelMessage(content=text, channel=channel, sender=sender)

        data = msg.pack()
        self.radio.send(data)

    #---------------------------------------------------------------------------
    def on_dccmsg(self, conn, event):
        self.logger.debug('DCC [MSG] -- %s', event)

    #---------------------------------------------------------------------------
    def on_dccchat(self, conn, event):
        self.logger.debug('DCC [CHAT] -- %s', event)

    #---------------------------------------------------------------------------
    def on_dcc(self, conn, event):
        self.logger.debug('DCC [CHAT] -- %s', event)

    #---------------------------------------------------------------------------
    def _radio_recv(self, radio, data):
        self.logger.debug('[radio] << %s', data)
        self.msgbuf.append(data)

    #---------------------------------------------------------------------------
    def _handle_message(self, mbuf, msg):
        if isinstance(msg, ChannelMessage):
            if msg.channel in self.channels:
                self.connection.notice(msg.channel, f'[{msg.sender}] {msg.content}')
            else:
                self.logger.debug('not on channel %s; discarding', msg.channel)

        else:
            self.logger.debug('unsupported message %s; discarding', type(msg))

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
            msg = TextMessage(content=text, sender=sender)
            data = msg.pack()
            self.radio.send(data)
            conn.privmsg(sender, 'Your message has been sent! 👍')

        else:
            conn.privmsg(sender, f'Sorry, I don\'t understand "{cmd}" 😞')

