##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import os
import sys

from juliet import Juliet

from . import irc
from . import radio

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
## MAIN ENTRY

config_file = 'juliet.cfg'
if len(sys.argv) > 1:
    config_file = sys.argv[1]

conf = load_config(config_file)
radio_conf = conf['radio']
server_conf = conf['server']


radio = radio.RadioComm(
    serial_port=radio_conf['port'],
    baud_rate=radio_conf['baud']
)

nick = server_conf['nickname']
host = server_conf['host']
port = server_conf['port']

jules = Juliet(name=nick, server=host, port=port, radio=radio)

#for channel in server_conf['channels']:
#    key = channel.get('key', None)
#    jules..join(channel['name'], key)

try:
    jules.start()
except KeyboardInterrupt:
    jules.disconnect('offline')

radio.close()

