# perform basic unit tests on server objects

import logging
import unittest

import juliet

# keep logging output to a minumim for testing
logging.basicConfig(level=logging.FATAL)

################################################################################
class ClientTest(unittest.TestCase):

    #---------------------------------------------------------------------------
    def test_BasicNickParsing(self):
        data = b':localhost NICK unittest'
        msg = juliet.Message.parse(data)

        self.assertEqual(msg.command, 'NICK')
        self.assertEqual(msg.prefix, 'localhost')

        self.assertIsNone(msg.remarks, None)

        self.assertEqual(len(msg.params), 1)
        self.assertEqual(msg.params[0], 'unittest')

    #---------------------------------------------------------------------------
    def test_BasicUserParsing(self):
        data = b'USER unittest * localhost :Unit Test'
        msg = juliet.Message.parse(data)

        self.assertIsNone(msg.prefix, None)

        self.assertEqual(msg.command, 'USER')
        self.assertEqual(msg.remarks, 'Unit Test')

        self.assertEqual(len(msg.params), 3)
        self.assertEqual(msg.params[0], 'unittest')
        self.assertEqual(msg.params[1], '*')
        self.assertEqual(msg.params[2], 'localhost')

    #---------------------------------------------------------------------------
    def test_BasicServerReply(self):
        data = b':localhost 002 juliet :Your host is unittest'
        msg = juliet.Message.parse(data)

        self.assertEqual(msg.prefix, 'localhost')

        self.assertEqual(msg.reply, 2)
        self.assertEqual(msg.remarks, 'Your host is unittest')

        self.assertEqual(len(msg.params), 1)
        self.assertEqual(msg.params[0], 'juliet')

