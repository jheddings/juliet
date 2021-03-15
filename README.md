# juliet #

A lightweight mesh IRC server for radio networks.  Although the primary use case is for
ham radio, `juliet` should perform well either as a simple standalone IRC server or as
part of a customized mesh environment.

Written by W0JHX.  Tested using Icom 92AD with the standard programming cable.

## Usage ##

## Configuration ##

See the sample `juliet.cfg` for documentation.

### Logging ###

Enable logging to help with troubleshooting.

## Technical Info ##

## Mesh Nodes ##

Configure using the full module name of the node, e.g. `juilet.node.NullMeshNode`.

### NullMeshNode ###

This node will never send or recieve data.  It is mostly used for testing or as a base
class for more interesting node types.

### LoopbackMeshNode ###

This node will receive all data it sends.  It is mostly used for testing.

### SerialMeshNode ###

This node will send and recieve messages over a serial port.

### Custom Mesh Nodes ##

Developers are able to build custom mesh nodes using the `juliet.MeshNode` base class.

See the existing node types for examples.

_-73_
