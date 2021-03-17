# main entry for juliet

import os
import sys

import juliet

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

config_file = sys.argv[1]
conf = load_config(config_file)

jules = juliet.Juliet()

client = irc.Client(nick='juliet')
jules.attach(client)

client.connect('defiant.local')

# TODO do at client.on_welcome
client.join('#CQCQCQ')
client.privmsg('#CQCQCQ', 'QSL?')

jules.start()

