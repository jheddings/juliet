# main entry for juliet

import os
import sys

import juliet

################################################################################
def parse_args():
    import argparse

    argp = argparse.ArgumentParser(description='juliet: a mesh IRC server for radio networks')

    argp.add_argument('--config', default='/etc/juliet.cfg',
                      help='configuration file (default: /etc/juliet.cfg)')

    argp.add_argument('--daemon', action='store_true',
                      help='run service as a daemon (default: False)')

    return argp.parse_args()

################################################################################
def load_config(args):
    import yaml
    import logging.config

    try:
        from yaml import CLoader as YamlLoader
    except ImportError:
        from yaml import Loader as YamlLoader

    config_file = args.config

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

    # TODO error checking on configuration

    return conf

################################################################################
## MAIN ENTRY

args = parse_args()
conf = load_config(args)

# TODO read config options

server = juliet.Server()

# TODO attach nodes
# TODO configure mesh

try:
    server.start()
except KeyboardInterrupt:
    server.stop()

