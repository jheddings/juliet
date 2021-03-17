# main entry for juliet

import os
import sys

from juliet import Juliet

from . import irc
from . import comm

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
if len(sys.argv) > 2:
    config_file = sys.argv[1]

conf = load_config(config_file)
radio_conf = conf['radio']
irc_conf = conf['servers']

radio = comm.RadioComm(
    serial_port=radio_conf['port'],
    baud_rate=radio_conf['baud']
)

jules = Juliet(comm=radio)

for server_conf in irc_conf:
    user = server_conf['username']
    nick = server_conf['nickname']
    name = server_conf['fullname']
    passwd = server_conf['password']
    host = server_conf['host']
    port = server_conf['port']

    client = irc.Client(nick=nick, name=name)
    jules.attach(client)

    client.connect(host, port=port, password=passwd)

    for channel in server_conf['channels']:
        key = channel.get('key', None)
        client.join(channel['name'], key)

jules.start()

radio.close()

