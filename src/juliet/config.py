##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import os
import sys

################################################################################
def load_config(config_file):
    import yaml
    import logging.config

    try:
        from yaml import CLoader as YamlLoader
    except ImportError:
        from yaml import Loader as YamlLoader

    if not os.path.exists(config_file):
        print(f'ERROR: config file does not exist: {config_file}')
        return None

    with open(config_file, 'r') as fp:
        conf = yaml.load(fp, Loader=YamlLoader)

        # determine if logging is already configured...
        root_logger = logging.getLogger()
        if not root_logger.hasHandlers():
            if 'logging' in conf:
                logging.config.dictConfig(conf['logging'])
            else:
                logging.basicConfig(level=logging.WARN)

    return conf

################################################################################
# XXX is there a standard way to handle app config files?
# sort of like Yamale combined with argparse? https://github.com/23andMe/Yamale
class UserConfig(object):

    #---------------------------------------------------------------------------
    # the port name for accessing the radio (required)
    @property

    def radio_port(self):
        if 'radio' not in g_conf:
            raise ValueError('missing "radio" in configuration')

        if 'port' not in g_conf['radio']:
            raise ValueError('missing radio port in configuration')

        return g_conf['radio']['port']

    #---------------------------------------------------------------------------
    # the baud rate when accessing the radio (default to 9600)
    @property

    def radio_baud(self):
        if 'radio' not in g_conf or 'baud' not in g_conf['radio']:
            return 9600

        if type(g_conf['radio']['baud']) is not int:
            raise ValueError('baud rate must be an integer')

        return g_conf['radio']['baud']

    #---------------------------------------------------------------------------
    # the hostname of the target IRC server (required)
    @property

    def irc_server_host(self):
        if 'server' not in g_conf:
            raise ValueError('missing "server" in configuration')

        if 'host' not in g_conf['server']:
            raise ValueError('missing IRC hostname in configuration')

        return g_conf['server']['host']

    #---------------------------------------------------------------------------
    # the port of the target IRC server (default to 6667)
    @property

    def irc_server_port(self):
        if 'server' not in g_conf or 'port' not in g_conf['server']:
            return 6667

        if type(g_conf['server']['port']) is not int:
            raise ValueError('IRC server port must be an integer')

        return g_conf['server']['port']

    #---------------------------------------------------------------------------
    # the nick & user for the IRC server (required)
    @property

    def irc_server_nick(self):
        if 'server' not in g_conf:
            raise ValueError('missing "server" in configuration')

        if 'nickname' not in g_conf['server']:
            raise ValueError('missing IRC nickname in configuration')

        return g_conf['server']['nickname']

    #---------------------------------------------------------------------------
    # the full name reported by the bot to the IRC server
    @property

    def irc_server_realname(self):
        if 'server' not in g_conf or 'realname' not in g_conf['server']:
            return None

        return g_conf['server']['realname']

    #---------------------------------------------------------------------------
    # the password used to join the IRC server (default to None)
    @property

    def irc_server_password(self):
        if 'server' not in g_conf or 'password' not in g_conf['server']:
            return None

        return g_conf['server']['password']

    #---------------------------------------------------------------------------
    # the default JOIN channels on the IRC server (default to None)
    @property

    def irc_channels(self):
        if 'server' not in g_conf or 'channels' not in g_conf['server']:
            return None

        channels = list()

        for chan in g_conf['server']['channels']:
            if 'name' not in chan:
                raise ValueError('missing channel name in configuration')

            if 'key' not in chan:
                chan['key'] = None

            channels.append(chan)

        return channels

################################################################################

if len(sys.argv) > 1:
    cfg_file = sys.argv[1]
else:
    cfg_file = 'juliet.cfg'

g_conf = load_config(cfg_file)

