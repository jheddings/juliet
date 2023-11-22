##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

import os
import sys


def load_config(config_file):
    import logging.config

    import yaml

    try:
        from yaml import CLoader as YamlLoader
    except ImportError:
        from yaml import Loader as YamlLoader

    if not os.path.exists(config_file):
        print(f"ERROR: config file does not exist: {config_file}")
        return None

    with open(config_file) as fp:
        conf = yaml.load(fp, Loader=YamlLoader)

        # determine if logging is already configured...
        root_logger = logging.getLogger()
        if not root_logger.hasHandlers():
            if "logging" in conf:
                logging.config.dictConfig(conf["logging"])
            else:
                logging.basicConfig(level=logging.WARN)

    return conf


class Default:
    # the port name for accessing the radio (required)
    RADIO_COMM_PORT = "/dev/tty.usbserial"

    # the baud rate when accessing the radio (default to 9600)
    RADIO_BAUD_RATE = 9600

    # the hostname of the target IRC server (required)
    IRC_SERVER_HOST = "localhost"

    # the port of the target IRC server (default to 6667)
    IRC_SERVER_PORT = 6667

    # the nick & user for the IRC server (required)
    IRC_NICKNAME = "juliet"

    # the full name reported by the bot to the IRC server
    IRC_REALNAME = "Juliet Radio Bot"

    # the password used to join the IRC server (default to None)
    IRC_PASSWORD = None

    # the default JOIN channels on the IRC server (default to None)
    IRC_CHANNELS = None

    def validate(self):
        if self.IRC_SERVER_HOST is None:
            raise ValueError("IRC server host must be specified")

        if self.IRC_SERVER_PORT is None:
            raise ValueError("IRC server port must be specified")

        if self.IRC_NICKNAME is None:
            raise ValueError("IRC nickname must be specified")

        if self.RADIO_COMM_PORT is None:
            raise ValueError("Radio port must be specified")

        if self.RADIO_BAUD_RATE is None:
            raise ValueError("Radio port must be specified")


class User(Default):
    def __init__(self):
        if "server" in g_conf:
            conf = g_conf["server"]

            self.IRC_SERVER_HOST = conf.get("host", "localhost")
            self.IRC_SERVER_PORT = conf.get("port", 6667)

            self.IRC_NICKNAME = conf.get("nickname", "juliet")
            self.IRC_REALNAME = conf.get("realname", "Juliet Radio Bot")
            self.IRC_PASSWORD = conf.get("password", None)

            self.IRC_CHANNELS = []

            for channel in conf.get("channels", None):
                if "name" not in channel:
                    raise ValueError("missing channel name in configuration")

                if "key" not in channel:
                    channel["key"] = None

                self.IRC_CHANNELS.append(channel)

        if "radio" in g_conf:
            conf = g_conf["radio"]

            self.RADIO_COMM_PORT = conf.get("port", None)
            self.RADIO_BAUD_RATE = conf.get("baud", 9600)

        self.validate()


if len(sys.argv) > 1:
    cfg_file = sys.argv[1]
else:
    cfg_file = "juliet.cfg"

g_conf = load_config(cfg_file)
