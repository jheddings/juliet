import logging

# helpful things for unit tests

# keep logging output to a minumim for testing
logging.basicConfig(level=logging.FATAL)

################################################################################
class InboxMixin(object):

    inbox = None

    #---------------------------------------------------------------------------
    def recv_msg(self, radio, data):
        if self.inbox is None:
            self.inbox = [ data ]
        else:
            self.inbox.append(data)

    #---------------------------------------------------------------------------
    def check_inbox(self, *expected):
        self.assertIsNotNone(self.inbox)
        self.assertEqual(len(expected), len(self.inbox))

        for idx in range(len(expected)):
            expect = expected[idx]
            msg = self.inbox[idx]
            self.assertEqual(expect, msg)

