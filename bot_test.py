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

@patch('keybase.send', return_value=(True, None))
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

    def send_message(self, incoming, mockKeybaseSend):
        conv = Conversation.lookup(TEST_CONV_ID, TEST_CONV_JSON, DB)
        message = keybase.Message.inject(incoming, TEST_USER, TEST_CONV_ID, TEST_CHANNEL, DB)
        resp = bot.process_message(self.config, message, conv)
        if resp is not None:
            keybase.send(TEST_CONV_ID, resp)

    def message_test(self, incoming, outgoing, mockKeybaseSend):
        self.send_message(incoming, mockKeybaseSend)
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

        mockNow.return_value = mockNow.return_value + timedelta
        bot.send_reminders(self.config)
        mockKeybaseSend.assert_called_with(TEST_CONV_ID, ":bell: *Reminder:* " + reminder)

    def test_set_reminder(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to foo tomorrow",
                "foo", "on Monday at 9:02 PM",
                "on Monday April 9 2018 at 9:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)

    @unittest.skip("todo")
    def test_set_reminder_without_to(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me foo tomorrow",
                "foo", "on Monday at 9:02 PM",
                "on Monday April 9 2018 at 9:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)

    # use separate functions for each reminder_test to reset the mocks and db
    def test_set_reminder_time_day(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to paint dan's fence at 10:30pm today",
                "paint dan's fence", "at 10:30 PM",
                "on Sunday April 8 2018 at 10:30 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    def test_set_reminder_day_time(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to paint dan's fence at 10:30",
                "paint dan's fence", "at 10:30 PM",
                "on Sunday April 8 2018 at 10:30 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    def test_set_reminder_pre_when(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me tuesday 8am to eat a quiche",
                "eat a quiche", "on Tuesday at 8:00 AM",
                "on Tuesday April 10 2018 at 8:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)

    def test_set_reminder_date(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me on april 21 to eat a quiche",
                "eat a quiche", "on Saturday April 21 at 12:00 AM",
                "on Saturday April 21 2018 at 12:00 AM",
                datetime.timedelta(days=30),
                mockNow, mockKeybaseSend)

    def test_reminder_listen(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me at 7:45 to listen to big song on speakers",
                "listen to big song on speakers", "on Monday at 7:45 PM",
                "on Monday April 9 2018 at 7:45 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)

    def test_reminder_relative(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to foo in 30 minutes.",
                "foo", "at 9:32 PM",
                "on Sunday April 8 2018 at 9:32 PM",
                datetime.timedelta(minutes=31),
                mockNow, mockKeybaseSend)

    def test_reminder_night(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to foo at 11",
                "foo", "at 11:00 PM",
                "on Sunday April 8 2018 at 11:00 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    def test_reminder_morning(self, mockNow, mockRandom, mockKeybaseSend):
        mockNow.return_value = NOW_UTC + datetime.timedelta(hours=12) # 9:02 AM
        self.reminder_test(
                "remind me to foo at 11",
                "foo", "at 11:00 AM",
                "on Monday April 9 2018 at 11:00 AM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    def test_reminder_3(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "set a reminder in 20 minutes to foo",
                "foo", "at 9:22 PM",
                "on Sunday April 8 2018 at 9:22 PM",
                datetime.timedelta(minutes=21),
                mockNow, mockKeybaseSend)

    def test_set_reminder_separate_when(self, mockNow, mockRandom, mockKeybaseSend):

        self.message_test("Remind me to say hello", bot.WHEN, mockKeybaseSend)
        mockKeybaseSend.assert_any_call(TEST_CONV_ID, bot.ASSUME_TZ)
        self.message_test("10pm", "Ok! I'll remind you to say hello at 10:00 PM", mockKeybaseSend)
        self.message_test("List", "Here are your upcoming reminders:\n\n"
                "1. say hello - on Sunday April 8 2018 at 10:00 PM\n", mockKeybaseSend)

        mockNow.return_value = NOW_UTC + datetime.timedelta(hours=1)
        bot.send_reminders(self.config)
        mockKeybaseSend.assert_called_with(TEST_CONV_ID, ":bell: *Reminder:* say hello")

    def test_set_reminder_not_before_now(self, mockNow, mockRandom, mockKeybaseSend):
        self.message_test("Remind me to say hello on January 1 2017", bot.WHEN, mockKeybaseSend)

    def test_set_timezone_during_when(self, mockNow, mockRandom, mockKeybaseSend):

        self.message_test("remind me to foo", bot.WHEN, mockKeybaseSend)
        mockKeybaseSend.assert_any_call(TEST_CONV_ID, bot.ASSUME_TZ)
        self.message_test("set my timezone to US/Pacific", bot.ACK_WHEN, mockKeybaseSend)
        self.message_test("tomorrow at 9am",
                "Ok! I'll remind you to foo at 9:00 AM", mockKeybaseSend)

    def test_set_timezone_after_reminder(self, mockNow, mockRandom, mockKeybaseSend):

        self.message_test("remind me to foo tomorrow at 9am",
                "Ok! I'll remind you to foo at 9:00 AM", mockKeybaseSend)
        mockKeybaseSend.assert_any_call(TEST_CONV_ID, bot.ASSUME_TZ)
        self.message_test("set my timezone to US/Pacific.", bot.ACK, mockKeybaseSend)
        self.message_test("list my reminders", "Here are your upcoming reminders:\n\n"
                "1. foo - on Monday April 9 2018 at 9:00 AM\n", mockKeybaseSend)

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
                "foo", "on Monday at 9:02 PM",
                "on Monday April 9 2018 at 9:02 PM",
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

    def test_undo(self, mockNow, mockRandom, mockKeybaseSend):
        self.message_test(
                "remind me to foo tomorrow",
                "Ok! I'll remind you to foo on Monday at 9:02 PM", mockKeybaseSend)
        self.message_test("nevermind", bot.OK, mockKeybaseSend)
        mockNow.return_value = NOW_UTC + datetime.timedelta(days=1)
        bot.send_reminders(self.config)
        mockKeybaseSend.assert_called_with(TEST_CONV_ID, bot.OK) # no reminder sent

    def snooze_test(self, mockNow, mockKeybaseSend, phrase, echo, duration):
        reminder = "get groceries"
        self.reminder_test(
            "remind me to get groceries tomorrow at 8am",
            reminder, "at 8:00 AM",
            "on Monday April 9 2018 at 8:00 AM",
            datetime.timedelta(days=1),
            mockNow, mockKeybaseSend)
        mockKeybaseSend.reset_mock()
        self.message_test(phrase, echo, mockKeybaseSend)
        mockKeybaseSend.reset_mock()
        mockNow.return_value = mockNow.return_value + duration - datetime.timedelta(minutes=1)
        bot.send_reminders(self.config)
        assert not mockKeybaseSend.called
        mockNow.return_value = mockNow.return_value + duration + datetime.timedelta(minutes=1)
        bot.send_reminders(self.config)
        mockKeybaseSend.assert_called_with(TEST_CONV_ID, ":bell: *Reminder:* " + reminder)

    def test_snooze_for(self, mockNow, mockRandom, mockKeybaseSend):
        self.snooze_test(mockNow, mockKeybaseSend, "snooze for 12 minutes",
                         "Ok. I'll remind you again in 12 minutes.", datetime.timedelta(minutes=12))

    # Snooze with a default of 10 minutes when the user doesn't specify a duration.
    def test_snooze(self, mockNow, mockRandom, mockKeybaseSend):
        self.snooze_test(mockNow, mockKeybaseSend, "snooze",
                         "Ok. I'll remind you again in 10 minutes.", datetime.timedelta(minutes=10))

    def test_snooze_nosep(self, mockNow, mockRandom, mockKeybaseSend):
        self.snooze_test(mockNow, mockKeybaseSend, "snooze 25min",
                         "Ok. I'll remind you again in 25min.", datetime.timedelta(minutes=25))

    def test_vacuum(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me to foo tomorrow",
                "foo", "on Monday at 9:02 PM",
                "on Monday April 9 2018 at 9:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 0
        self.reminder_test(
                "remind me to foo tomorrow",
                "foo", "on Tuesday at 9:02 PM",
                "on Tuesday April 10 2018 at 9:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 1
        self.message_test("snooze for 12 minutes",
             "Ok. I'll remind you again in 12 minutes.", mockKeybaseSend)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 0
        mockNow.return_value = mockNow.return_value + datetime.timedelta(minutes=15)
        bot.send_reminders(self.config)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 0
        self.message_test("remind me to foo tomorrow",
            "Ok! I'll remind you to foo on Wednesday at 9:17 PM", mockKeybaseSend)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 1

    def delete_test(self, delete_text, reminder_text, mockKeybaseSend):
        self.send_message("remind me to do something else on Tuesday", mockKeybaseSend)
        self.send_message(reminder_text, mockKeybaseSend)
        self.send_message(delete_text, mockKeybaseSend)
        assert mockKeybaseSend.call_args[0] != bot.UNKNOWN
        list_output = "Here are your upcoming reminders:\n\n1. do something else - on Tuesday April 10 2018 at 12:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)
        self.send_message("delete reminder #1", mockKeybaseSend)
    
    def test_delete(self, mockNow, mockRandom, mockKeybaseSend):
        reminder = "remind me to foo tomorrow"

        self.delete_test("delete the foo reminder", reminder, mockKeybaseSend)
        self.delete_test("delete the reminder to foo", reminder, mockKeybaseSend)
        self.delete_test("delete the reminder for 9:02pm tomorrow", reminder, mockKeybaseSend)
        self.delete_test("delete reminder # 1", reminder, mockKeybaseSend)
        self.delete_test("delete reminder 1", reminder, mockKeybaseSend)

    def test_delete_response(self, mockNow, mockRandom, mockKeybaseSend):
        self.send_message("remind me to foo in 1 hour", mockKeybaseSend)
        self.message_test("delete the foo reminder",
            "Alright, I've deleted the reminder to foo that was set for 10:02 PM.", mockKeybaseSend)

        self.send_message("remind me to beep on Sunday", mockKeybaseSend)
        self.message_test("delete the beep reminder",
            "Alright, I've deleted the reminder to beep that was set for Sunday at 12:00 AM.", mockKeybaseSend)

    def test_delete_undo(self, mockNow, mockRandom, mockKeybaseSend):
        self.send_message("remind me to foo tomorrow", mockKeybaseSend)
        self.send_message("delete the foo reminder", mockKeybaseSend)
        self.message_test("undo", bot.OK, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. foo - on Monday April 9 2018 at 9:02 PM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me every tuesday 8am to eat a quiche",
                "eat a quiche", "every week on Tuesday at 8:00 AM",
                "every week on Tuesday at 8:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every week on Tuesday at 8:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating_preppy(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me on every tuesday at 8am to eat a quiche",
                "eat a quiche", "every week on Tuesday at 8:00 AM",
                "every week on Tuesday at 8:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every week on Tuesday at 8:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating_every_other(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me on every other tuesday to eat a quiche",
                "eat a quiche", "every 2 weeks on Tuesday at 12:00 AM",
                "every 2 weeks on Tuesday at 12:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every 2 weeks on Tuesday at 12:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating_every_other_with_time(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me on every other tuesday at 10am to eat a quiche",
                "eat a quiche", "every 2 weeks on Tuesday at 10:00 AM",
                "every 2 weeks on Tuesday at 10:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every 2 weeks on Tuesday at 10:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating_nth(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me every 6 hours to eat a quiche",
                "eat a quiche", "every 6 hours",
                "every 6 hours",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every 6 hours\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating_snooze(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me every tuesday 8am to eat a quiche",
                "eat a quiche", "every week on Tuesday at 8:00 AM",
                "every week on Tuesday at 8:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        self.send_message("snooze for 20 minutes", mockKeybaseSend)

        # snoozed message shows up
        list_output = "Here are your upcoming reminders:\n\n" \
            "1. eat a quiche - on Tuesday April 10 2018 at 9:22 PM\n" \
            "2. eat a quiche - every week on Tuesday at 8:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

        # and the message was snoozed
        mockNow.return_value = mockNow.return_value + datetime.timedelta(minutes=21)
        bot.send_reminders(self.config)
        mockKeybaseSend.assert_called_with(TEST_CONV_ID, ":bell: *Reminder:* eat a quiche")

        # and the repetition still happens
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every week on Tuesday at 8:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating_weekday(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me every weekday at 6pm to eat a quiche",
                "eat a quiche", "every weekday at 6:00 PM",
                "every weekday at 6:00 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every weekday at 6:00 PM\n"
        self.message_test("list", list_output, mockKeybaseSend)
        # 4 weekdays
        for i in range(4):
            mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
            bot.send_reminders(self.config)
            mockKeybaseSend.assert_called_with(TEST_CONV_ID, ":bell: *Reminder:* eat a quiche")
        
        # saturday
        mockKeybaseSend.reset_mock()
        mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
        bot.send_reminders(self.config)
        assert not mockKeybaseSend.called

        # sunday
        mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
        bot.send_reminders(self.config)
        assert not mockKeybaseSend.called

        # monday
        mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
        bot.send_reminders(self.config)
        mockKeybaseSend.assert_called_with(TEST_CONV_ID, ":bell: *Reminder:* eat a quiche")

    def test_repeating_year(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me every year on january 1 to have a great year",
                "have a great year", "every year on January 1 at 12:00 AM",
                "every year on January 1 at 12:00 AM",
                datetime.timedelta(days=365),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. have a great year - every year on January 1 at 12:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating_month(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me every month on the 30th at 12:00 AM to pay the rent",
                "pay the rent", "every month on the 30th at 12:00 AM",
                "every month on the 30th at 12:00 AM",
                datetime.timedelta(days=30),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. pay the rent - every month on the 30th at 12:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating_week_day(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me every week day at 8am to wake up",
                "wake up", "every weekday at 8:00 AM",
                "every weekday at 8:00 AM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. wake up - every weekday at 8:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    # Bot used to assume 12:00 AM but now asks for clarification on time.
    # The new behavior is better. Test should be udpated.
    @unittest.skip("outdated")
    def test_repeating_week_day_2(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "remind me every week day to wake up",
                "wake up", "every weekday at 12:00 AM",
                "every weekday at 12:00 AM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. wake up - every weekday at 12:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

    def test_repeating_sunday(self, mockNow, mockRandom, mockKeybaseSend):
        self.reminder_test(
                "Remind me every Sunday at 11am to water the plant",
                "water the plant", "every week on Sunday at 11:00 AM",
                "every week on Sunday at 11:00 AM",
                datetime.timedelta(days=7),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. water the plant - every week on Sunday at 11:00 AM\n"
        self.message_test("list", list_output, mockKeybaseSend)

        # 1 more day
        mockKeybaseSend.reset_mock()
        mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
        bot.send_reminders(self.config)
        assert not mockKeybaseSend.called


if __name__ == '__main__':
    unittest.main()
