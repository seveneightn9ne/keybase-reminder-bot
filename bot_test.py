import datetime, pytz, sqlite3, unittest
from mock import patch

import bot, conversation, keybase, reminders
from conversation import Conversation
from user import User

DB = 'test.db' # Why doesn't :memory: work?
TEST_BOT = '__testbot__'
TEST_USER = '__testuser__'
TEST_OWNER = '__testowner__'
TEST_CHANNEL = TEST_USER + "," + TEST_BOT
NOW_TS = 1523235748.0 # April 8 2018, 21:02:28 EDT. April 9 2018, 01:02:28 UTC.

class TestBot(unittest.TestCase):

    @patch('subprocess.check_call')
    @patch('keybase.status')
    def setUp(self, mockKeybaseStatus, mockCheckCall):
        mockKeybaseStatus.return_value = {"LoggedIn": True, "Username": TEST_BOT}
        self.config = bot.Config(DB, TEST_BOT, TEST_OWNER)
        self.now = datetime.datetime.fromtimestamp(NOW_TS, tz=pytz.utc)
        bot.setup(self.config)

    def tearDown(self):
        conv = Conversation.lookup(TEST_CHANNEL, DB)
        conv.delete()
        user = User.lookup(TEST_USER, DB)
        user.delete()

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
    @patch('random.choice')
    @patch('datetime.datetime')
    def test_set_reminder(self, mockDatetime, mockRandomChoice, mockKeybaseSend):
        mockKeybaseSend.return_value = True
        mockRandomChoice.side_effect = lambda i: i[0]
        mockDatetime.now.return_value = self.now

        conv = Conversation.lookup(TEST_CHANNEL, DB)
        message = keybase.Message.inject("remind me to foo tomorrow", TEST_USER, TEST_CHANNEL, DB)
        bot.process_message(self.config, message, conv)
        mockKeybaseSend.assert_any_call(TEST_CHANNEL, bot.ASSUME_TZ)
        mockKeybaseSend.assert_called_with(TEST_CHANNEL,
            "Ok! I'll remind you to foo on Monday at 09:02 PM")

    @patch('keybase.send')
    @patch('random.choice')
    def test_set_timezone_during_when(self, mockRandomChoice, mockKeybaseSend):
        mockKeybaseSend.return_value = True
        mockRandomChoice.side_effect = lambda i: i[0]

        conv = Conversation.lookup(TEST_CHANNEL, DB)
        message = keybase.Message.inject("remind me to foo", TEST_USER, TEST_CHANNEL, DB)
        bot.process_message(self.config, message, conv)
        mockKeybaseSend.assert_any_call(TEST_CHANNEL, bot.ASSUME_TZ)
        mockKeybaseSend.assert_called_with(TEST_CHANNEL, bot.WHEN)

        message = keybase.Message.inject("set my timezone to US/Pacific.",
                TEST_USER, TEST_CHANNEL, DB)
        bot.process_message(self.config, message, conv)
        mockKeybaseSend.assert_called_with(TEST_CHANNEL, bot.ACK_WHEN)

        message = keybase.Message.inject("tomorrow at 9am", TEST_USER, TEST_CHANNEL, DB)
        bot.process_message(self.config, message, conv)
        mockKeybaseSend.assert_called_with(TEST_CHANNEL,
            "Ok! I'll remind you to foo on Monday at 09:00 AM")

    @patch('keybase.send')
    def test_set_timezone_after_reminder(self, mockKeybaseSend):
        mockKeybaseSend.return_value = True

if __name__ == '__main__':
    unittest.main()
