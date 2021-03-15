##
# juliet - a lightweight mesh IRC server for radio networks
##

VERSION = '0.0.1'

# expose top-level classes to 3rd parties
from .server import Server
from .node import MeshNode
from .event import Event

