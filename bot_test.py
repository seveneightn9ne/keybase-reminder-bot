import sqlite3, unittest
from mock import patch

import bot, keybase
from conversation import Conversation

DB = 'test.db' # Why doesn't :memory: work?
TEST_BOT = '__testbot__'
TEST_USER = '__testuser__'
TEST_OWNER = '__testowner__'
TEST_CHANNEL = TEST_USER + "," + TEST_BOT

class TestBot(unittest.TestCase):

    @patch('subprocess.check_call')
    @patch('keybase.status')
    def setUp(self, mockKeybaseStatus, mockCheckCall):
        mockKeybaseStatus.return_value = {"LoggedIn": True, "Username": TEST_BOT}
        self.config = bot.Config(DB, TEST_BOT, TEST_OWNER)
        bot.setup(self.config)

    @patch('keybase.send')
    def test_recent_message(self, mockKeybaseSend):
        # When bot receives two messages in a row, it shouldn't send the full help message twice.
        mockKeybaseSend.return_value = True

        conv = Conversation.lookup(TEST_CHANNEL, DB)
        message = keybase.Message.inject('not parsable', TEST_USER, TEST_CHANNEL, DB)

        bot.process_message(self.config, message, conv)
        mockKeybaseSend.assert_called_with(TEST_CHANNEL, bot.PROMPT_HELP)

        bot.process_message(self.config, message, conv)
        mockKeybaseSend.assert_called_with(TEST_CHANNEL, bot.UNKNOWN)

    @patch('keybase.send')
    def test_set_reminder(self, mockKeybaseSend):
        mockKeybaseSend.return_value = True



if __name__ == '__main__':
    unittest.main()
