# juliet #

Juliet is an IRC bot that exchanges channel messages over a radio network.  The intended
use for this bot is to enable communications by amateur radio operators when standard
infrastrastructure is not available.  While it was designed with D-STAR in mind, any
radio capable of exchanging data over a standard serial port _should_ work.

Written by W0JHX.  Tested using Icom 92AD with the standard programming cable.

## Usage ##

```
python3 -m juliet
```

- Connect to your radio's serial interface (or programming cable).
- Create a configurtion file (see Configuration below)
- Run the `juliet` module, optionally specifying a configuration file.
- Connect to the computer in a standard browser.

Messages will be displayed automatically when they are recieved.

Outgoing messages will be rate limited to 1 line per second.  This is primarily to help
avoid frequency congenstion.

## Configuration ##

TODO - more information here...

### Logging ###

Enable logging to help with troubleshooting.

## Technical Info ##

It is hard to find information online about some of this stuff, so here is some detail
that I've uncovered along the way.  Note that this is not intended to be a complete
reference for using D-STAR, just some useful information while writing this application.

### Connecting to the radio ###

D-STAR radios typically have a serial port for programming.  This port will also accept and
relay data from the radio.  In most cases, simply opening the serial port is enough to
access low-bandwidth data from the radio.

Some radios must be placed in "Auto TX" mode (rather than PTT) in order to send any serial
data automatically.

Also, be sure to disable automatic GPS reporting when using a radio with Juliet.  This will
mangle the data stream such that it cannot be parsed.

### D-STAR data format ###

The D-STAR spec does not define any structure for the data stream, leaving it up to each
application.  Most radios use a similar format for transmitting GPS data.  You may see these
messages in the log file, but they are ignored by Juliet.

### Juliet message format ###

**WORK IN PROGRESS**

```
>>{version}:{crc16}:{sender}:{timestamp}:{content}:{signature}<<
```

* `version` (required) - specify the version of the message structure - see below
* `crc16` (required) - the checksum for the message (sender, content, sequence, signature)
* `sender` (required) - the sender of the message, specified in config (not the radio MY call)
* `timestamp` (required) - the timestamp when the message was sent
* `content` (required) - main content of the message; length of the message is not restricted
* `signature` (optional) - digital signature used to authenticate the sender

#### Message Types ####

The `version` field denotes both message structure as well as content type.

* 0 - uncompressed text
* 1 - compressed & base-64 encoded text
* 3 - channel text
* 7 - file message - currently unused, but here for completeness

_-73_
