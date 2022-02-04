##
# juliet - Copyright (c) Jason Heddings. All rights reserved.
# Licensed under the MIT License. See LICENSE for full terms.
##

# modified from https://stackoverflow.com/a/2022629/197772
class Event(list):
    def __iadd__(self, handler):
        self.append(handler)
        return self

    def __isub__(self, handler):
        self.remove(handler)
        return self

    def __call__(self, *args, **kwargs):
        for handler in self:
            handler(*args, **kwargs)

    def __repr__(self):
        return "Event(%s)" % list.__repr__(self)
