import datetime, pytz, sqlite3, unittest
import mock
from mock import patch

import bot, conversation, keybase, reminders, parse
from conversation import Conversation
from user import User

DB = 'test.db' # Why doesn't :memory: work?
TEST_BOT = '__testbot__'
TEST_USER = '__testuser__'
TEST_OWNER = '__testowner__'
TEST_CHANNEL = TEST_USER + "," + TEST_BOT
TEST_CONV_ID = "0001"
TEST_CHANNEL_JSON = {"name": TEST_CHANNEL, "members_type": "impteamnative"}
TEST_CONV_JSON = {"id": TEST_CONV_ID, "channel": TEST_CHANNEL_JSON}
NOW_TS = 1523235748.0 # Sunday April 8 2018, 21:02:28 EDT. Monday April 9 2018, 01:02:28 UTC.
NOW_UTC = datetime.datetime.fromtimestamp(NOW_TS, tz=pytz.utc)

@patch('keybase.send', return_value=True)
@patch('random.choice', side_effect=lambda i: i[0])
@patch('util.now_utc', return_value=NOW_UTC)
class TestBot(unittest.TestCase):

    @patch('subprocess.check_call')
    @patch('keybase._status')
    def setUp(self, mockKeybaseStatus, mockCheckCall):
        mockKeybaseStatus.return_value = {"LoggedIn": True, "Username": TEST_BOT}
        self.config = bot.Config(DB, TEST_BOT, TEST_OWNER)
        self.now = datetime.datetime.fromtimestamp(NOW_TS, tz=pytz.utc)
        bot.setup(self.config)

    def tearDown(self):
        conv = Conversation.lookup(TEST_CONV_ID, TEST_CONV_JSON, DB)
        conv.delete()
        user = User.lookup(TEST_USER, DB)
        user.delete()

    def message_test(self, incoming, outgoing, mockKeybaseSend):
        conv = Conversation.lookup(TEST_CONV_ID, TEST_CONV_JSON, DB)
        message = keybase.Message.inject(incoming, TEST_USER, TEST_CONV_ID, TEST_CHANNEL, DB)
        bot.process_message(self.config, message, conv)
        mockKeybaseSend.assert_called_with(TEST_CONV_ID, outgoing)

    def test_recent_message(self, mockNow, mockRandom, mockKeybaseSend):
        # When bot receives two messages in a row, it shouldn't send the full help message twice.
        self.message_test(u'not parsable', bot.PROMPT_HELP, mockKeybaseSend)
        mockNow.return_value = mockNow.return_value + datetime.timedelta(minutes=1)
        self.message_test(u'not parsable', bot.UNKNOWN, mockKeybaseSend)

    def reminder_test(self, text, reminder, whentext, fullwhen, timedelta, mockNow, mockKeybaseSend):
        self.message_test(text,
                "Ok! I'll remind you to " + reminder + " " + whentext, mockKeybaseSend)
        mockKeybaseSend.assert_any_call(TEST_CONV_ID, bot.ASSUME_TZ)

        self.message_test("list", "Here are your upcoming reminders:\n\n"
                "1. " + reminder + " - " + fullwhen + "\n", mockKeybaseSend)

        mockNow.return_value = NOW_UTC + timedelta
        bot.send_reminders(self.config)
        mockKeybaseSend.assert_called_with(TEST_CONV_ID, ":bell: *Reminder:* " + reminder)

    def test_set_reminder(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to foo tomorrow",
                "foo", "on Monday at 09:02 PM",
                "on Monday April 09 2018 at 09:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)

    # use separate functions for each reminder_test to reset the mocks and db
    def test_set_reminder_time_day(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to paint dan's fence at 10:30pm today",
                "paint dan's fence", "at 10:30 PM",
                "on Sunday April 08 2018 at 10:30 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    def test_set_reminder_day_time(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to paint dan's fence at 10:30",
                "paint dan's fence", "at 10:30 PM",
                "on Sunday April 08 2018 at 10:30 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    def test_set_reminder_day_time(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to paint dan's fence today at 10:30pm",
                "paint dan's fence", "at 10:30 PM",
                "on Sunday April 08 2018 at 10:30 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    def test_set_reminder_pre_when(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me tuesday 8am to eat a quiche",
                "eat a quiche", "on Tuesday at 08:00 AM",
                "on Tuesday April 10 2018 at 08:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)

    def test_set_reminder_date(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me on april 21 to eat a quiche",
                "eat a quiche", "on Saturday April 21 at 12:00 AM",
                "on Saturday April 21 2018 at 12:00 AM",
                datetime.timedelta(days=30),
                mockNow, mockKeybaseSend)

    def test_set_reminder_separate_when(self, mockNow, mockRandom, mockKeybaseSend):

        self.message_test("Remind me to say hello", bot.WHEN, mockKeybaseSend)
        mockKeybaseSend.assert_any_call(TEST_CONV_ID, bot.ASSUME_TZ)
        self.message_test("10pm", "Ok! I'll remind you to say hello at 10:00 PM", mockKeybaseSend)
        self.message_test("List", "Here are your upcoming reminders:\n\n"
                "1. say hello - on Sunday April 08 2018 at 10:00 PM\n", mockKeybaseSend)

        mockNow.return_value = NOW_UTC + datetime.timedelta(hours=1)
        bot.send_reminders(self.config)
        mockKeybaseSend.assert_called_with(TEST_CONV_ID, ":bell: *Reminder:* say hello")

    def test_set_timezone_during_when(self, mockNow, mockRandom, mockKeybaseSend):

        self.message_test("remind me to foo", bot.WHEN, mockKeybaseSend)
        mockKeybaseSend.assert_any_call(TEST_CONV_ID, bot.ASSUME_TZ)
        self.message_test("set my timezone to US/Pacific", bot.ACK_WHEN, mockKeybaseSend)
        self.message_test("tomorrow at 9am",
                "Ok! I'll remind you to foo at 09:00 AM", mockKeybaseSend)

    def test_set_timezone_after_reminder(self, mockNow, mockRandom, mockKeybaseSend):

        self.message_test("remind me to foo tomorrow at 9am",
                "Ok! I'll remind you to foo at 09:00 AM", mockKeybaseSend)
        mockKeybaseSend.assert_any_call(TEST_CONV_ID, bot.ASSUME_TZ)
        self.message_test("set my timezone to US/Pacific.", bot.ACK, mockKeybaseSend)
        self.message_test("list my reminders", "Here are your upcoming reminders:\n\n"
                "1. foo - on Monday April 09 2018 at 09:00 AM\n", mockKeybaseSend)

    def test_parse_source(self, mockNow, mockRandom, mockKeybaseSend):
        self.message_test(" What are you made of", bot.SOURCE, mockKeybaseSend)
        self.message_test(" What are you made of??", bot.SOURCE, mockKeybaseSend)

    def test_help(self, mockNow, mockRandom, mockKeybaseSend):
        self.message_test("help", bot.HELP % TEST_OWNER, mockKeybaseSend)

    def test_hello(self, mockNow, mockRandom, mockKeybaseSend):
        self.message_test("hi", "hi!", mockKeybaseSend)

        conv = Conversation.lookup(TEST_CONV_ID, TEST_CONV_JSON, DB)
        conv.delete()

        self.message_test("hello", "hello!", mockKeybaseSend)

    def test_ack(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to foo tomorrow",
                "foo", "on Monday at 09:02 PM",
                "on Monday April 09 2018 at 09:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        # Asserts that bot didn't send any message since the reminder
        self.message_test("thanks", ":bell: *Reminder:* foo", mockKeybaseSend)

    def test_stfu(self, mockNow, mockRandom, mockKeybaseSend):
        self.message_test("remind me to foo", bot.WHEN, mockKeybaseSend)
        self.message_test("unparsable", bot.HELP_WHEN, mockKeybaseSend)
        self.message_test("unparsable", bot.HELP_WHEN, mockKeybaseSend)
        self.message_test("stfu", bot.OK, mockKeybaseSend)
        self.message_test("unparsable", bot.UNKNOWN, mockKeybaseSend)

    def test_no_stfu(self, mockNow, mockRandom, mockKeybaseSend):
        self.message_test(
                "remind me to foo tomorrow",
                "Ok! I'll remind you to foo on Monday at 09:02 PM", mockKeybaseSend)
        self.message_test("nevermind", bot.UNKNOWN, mockKeybaseSend)


if __name__ == '__main__':
    unittest.main()
