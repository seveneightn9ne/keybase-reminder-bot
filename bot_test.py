import datetime, pytz, sqlite3, unittest
import mock
from mock import patch

import bot, conversation, keybase, parse
from conversation import Conversation
from user import User
from reminders import get_due_reminders, Reminder

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

@patch('keybase.send')
@patch('random.choice', side_effect=lambda i: i[0])
@patch('util.now_utc', return_value=NOW_UTC)
class TestBot(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.config = bot.Config(DB, TEST_BOT, TEST_OWNER)
        self.now = datetime.datetime.fromtimestamp(NOW_TS, tz=pytz.utc)
        self.bot = bot.setup(self.config)

    def tearDown(self):
        conv = Conversation.lookup_or_json(TEST_CONV_ID, TEST_CONV_JSON, DB)
        conv.delete()
        user = User.lookup(TEST_USER, DB)
        user.delete()

    async def send_message(self, incoming, mockKeybaseSend):
        conv = Conversation.lookup_or_json(TEST_CONV_ID, TEST_CONV_JSON, DB)
        message = keybase.Message.inject(incoming, TEST_USER, TEST_CONV_ID, TEST_CHANNEL, DB)
        await bot.process_message(self.bot, self.config, message, conv)

    async def message_test(self, incoming, outgoing, mockKeybaseSend):
        await self.send_message(incoming, mockKeybaseSend)
        mockKeybaseSend.assert_called_with(self.bot, TEST_CONV_ID, outgoing)

    async def test_recent_message(self, mockNow, mockRandom, mockKeybaseSend):
        # When bot receives two messages in a row, it shouldn't send the full help message twice.
        await self.message_test('not parsable', bot.PROMPT_HELP, mockKeybaseSend)
        mockNow.return_value = mockNow.return_value + datetime.timedelta(minutes=1)
        await self.message_test('not parsable', bot.UNKNOWN, mockKeybaseSend)

    async def reminder_test(self, text, reminder, whentext, fullwhen, timedelta, mockNow, mockKeybaseSend):
        await self.message_test(text,
                "Ok! I'll remind you to " + reminder + " " + whentext, mockKeybaseSend)
        mockKeybaseSend.assert_any_call(self.bot, TEST_CONV_ID, bot.ASSUME_TZ)

        await self.message_test("list", "Here are your upcoming reminders:\n\n"
                "1. " + reminder + " - " + fullwhen + "\n", mockKeybaseSend)

        mockNow.return_value = mockNow.return_value + timedelta
        await bot.send_reminders(self.bot, self.config)
        mockKeybaseSend.assert_called_with(self.bot, TEST_CONV_ID, ":bell: *Reminder:* " + reminder)

    async def test_set_reminder(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to foo tomorrow",
                "foo", "on Monday at 9:02 PM",
                "on Monday April 9 2018 at 9:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)

    @unittest.skip("todo")
    async def test_set_reminder_without_to(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me foo tomorrow",
                "foo", "on Monday at 9:02 PM",
                "on Monday April 9 2018 at 9:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)

    # use separate functions for each reminder_test to reset the mocks and db
    async def test_set_reminder_time_day(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to paint dan's fence at 10:30pm today",
                "paint dan's fence", "at 10:30 PM",
                "on Sunday April 8 2018 at 10:30 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    async def test_set_reminder_day_time(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to paint dan's fence at 10:30",
                "paint dan's fence", "at 10:30 PM",
                "on Sunday April 8 2018 at 10:30 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    @unittest.skip("jess disagrees")
    async def test_set_reminder_rollover(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to paint dan's fence at 8:30",
                "paint dan's fence", "at 8:30 AM",
                "on Monday April 9 2018 at 8:30 AM",
                datetime.timedelta(hours=12),
                mockNow, mockKeybaseSend)

    async def test_set_reminder_24_time(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to paint dan's fence at 22:30",
                "paint dan's fence", "at 10:30 PM",
                "on Sunday April 8 2018 at 10:30 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    async def test_set_reminder_24_time_2(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to paint dan's fence at 08:30",
                "paint dan's fence", "at 8:30 AM",
                "on Monday April 9 2018 at 8:30 AM",
                datetime.timedelta(hours=12),
                mockNow, mockKeybaseSend)

    async def test_set_reminder_24_time_3(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to paint dan's fence at 22",
                "paint dan's fence", "at 10:00 PM",
                "on Sunday April 8 2018 at 10:00 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    async def test_set_reminder_24_time_4(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to paint dan's fence at 08",
                "paint dan's fence", "at 8:00 AM",
                "on Monday April 9 2018 at 8:00 AM",
                datetime.timedelta(hours=12),
                mockNow, mockKeybaseSend)

    async def test_set_reminder_24_time_5(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test("remind me to paint dan's fence at 24:30",
            "When do you want to be reminded?", mockKeybaseSend)

    async def test_set_reminder_24_time_6(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test("remind me to paint dan's fence at 14:00 am",
            "When do you want to be reminded?", mockKeybaseSend)

    async def test_set_reminder_pre_when(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me tuesday 8am to eat a quiche",
                "eat a quiche", "on Tuesday at 8:00 AM",
                "on Tuesday April 10 2018 at 8:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)

    async def test_set_reminder_date(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me on april 21 to eat a quiche",
                "eat a quiche", "on Saturday April 21 at 12:00 AM",
                "on Saturday April 21 2018 at 12:00 AM",
                datetime.timedelta(days=30),
                mockNow, mockKeybaseSend)

    async def test_reminder_listen(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me at 7:45 to listen to big song on speakers",
                "listen to big song on speakers", "on Monday at 7:45 PM",
                "on Monday April 9 2018 at 7:45 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)

    async def test_reminder_relative(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to foo in 30 minutes.",
                "foo", "at 9:32 PM",
                "on Sunday April 8 2018 at 9:32 PM",
                datetime.timedelta(minutes=31),
                mockNow, mockKeybaseSend)

    async def test_reminder_night(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to foo at 11",
                "foo", "at 11:00 PM",
                "on Sunday April 8 2018 at 11:00 PM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    async def test_reminder_morning(self, mockNow, mockRandom, mockKeybaseSend):
        mockNow.return_value = NOW_UTC + datetime.timedelta(hours=12) # 9:02 AM
        await self.reminder_test(
                "remind me to foo at 11",
                "foo", "at 11:00 AM",
                "on Monday April 9 2018 at 11:00 AM",
                datetime.timedelta(hours=2),
                mockNow, mockKeybaseSend)

    async def test_reminder_3(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "set a reminder in 20 minutes to foo",
                "foo", "at 9:22 PM",
                "on Sunday April 8 2018 at 9:22 PM",
                datetime.timedelta(minutes=21),
                mockNow, mockKeybaseSend)

    async def test_set_reminder_separate_when(self, mockNow, mockRandom, mockKeybaseSend):

        await self.message_test("Remind me to say hello", bot.WHEN, mockKeybaseSend)
        mockKeybaseSend.assert_any_call(self.bot, TEST_CONV_ID, bot.ASSUME_TZ)
        await self.message_test("10pm", "Ok! I'll remind you to say hello at 10:00 PM", mockKeybaseSend)
        await self.message_test("List", "Here are your upcoming reminders:\n\n"
                "1. say hello - on Sunday April 8 2018 at 10:00 PM\n", mockKeybaseSend)

        mockNow.return_value = NOW_UTC + datetime.timedelta(hours=1)
        await bot.send_reminders(self.bot, self.config)
        mockKeybaseSend.assert_called_with(self.bot, TEST_CONV_ID, ":bell: *Reminder:* say hello")

    async def test_set_reminder_not_before_now(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test("Remind me to say hello on January 1 2017", bot.WHEN, mockKeybaseSend)

    async def test_set_timezone_during_when(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test("remind me to foo", bot.WHEN, mockKeybaseSend)
        mockKeybaseSend.assert_any_call(self.bot, TEST_CONV_ID, bot.ASSUME_TZ)
        await self.message_test("set my timezone to US/Pacific", bot.ACK_WHEN, mockKeybaseSend)
        await self.message_test("tomorrow at 9am",
                "Ok! I'll remind you to foo at 9:00 AM", mockKeybaseSend)

    async def test_set_timezone_after_reminder(self, mockNow, mockRandom, mockKeybaseSend):

        await self.message_test("remind me to foo tomorrow at 9am",
                "Ok! I'll remind you to foo at 9:00 AM", mockKeybaseSend)
        mockKeybaseSend.assert_any_call(self.bot, TEST_CONV_ID, bot.ASSUME_TZ)
        await self.message_test("set my timezone to US/Pacific.", bot.ACK, mockKeybaseSend)
        await self.message_test("list my reminders", "Here are your upcoming reminders:\n\n"
                "1. foo - on Monday April 9 2018 at 9:00 AM\n", mockKeybaseSend)

    async def test_parse_source(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test(" What are you made of", bot.SOURCE, mockKeybaseSend)
        await self.message_test(" What are you made of??", bot.SOURCE, mockKeybaseSend)

    async def test_help(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test("help", bot.HELP % TEST_OWNER, mockKeybaseSend)

    async def test_hello(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test("hi", "hi!", mockKeybaseSend)

        conv = Conversation.lookup_or_json(TEST_CONV_ID, TEST_CONV_JSON, DB)
        conv.delete()

        await self.message_test("hello", "hello!", mockKeybaseSend)

    async def test_ack(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to foo tomorrow",
                "foo", "on Monday at 9:02 PM",
                "on Monday April 9 2018 at 9:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        # Asserts that bot didn't send any message since the reminder
        await self.message_test("thanks", ":bell: *Reminder:* foo", mockKeybaseSend)

    async def test_stfu(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test("remind me to foo", bot.WHEN, mockKeybaseSend)
        await self.message_test("unparsable", bot.HELP_WHEN, mockKeybaseSend)
        await self.message_test("unparsable", bot.HELP_WHEN, mockKeybaseSend)
        await self.message_test("stfu", bot.OK, mockKeybaseSend)
        await self.message_test("unparsable", bot.UNKNOWN, mockKeybaseSend)

    async def test_undo(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test(
                "remind me to foo tomorrow",
                "Ok! I'll remind you to foo on Monday at 9:02 PM", mockKeybaseSend)
        await self.message_test("nevermind", bot.OK, mockKeybaseSend)
        mockNow.return_value = NOW_UTC + datetime.timedelta(days=1)
        await bot.send_reminders(self.bot, self.config)
        mockKeybaseSend.assert_called_with(self.bot, TEST_CONV_ID, bot.OK) # no reminder sent

    async def snooze_test(self, mockNow, mockKeybaseSend, phrase, echo, duration):
        reminder = "get groceries"
        await self.reminder_test(
            "remind me to get groceries tomorrow at 8am",
            reminder, "at 8:00 AM",
            "on Monday April 9 2018 at 8:00 AM",
            datetime.timedelta(days=1),
            mockNow, mockKeybaseSend)
        mockKeybaseSend.reset_mock()
        await self.message_test(phrase, echo, mockKeybaseSend)
        mockKeybaseSend.reset_mock()
        mockNow.return_value = mockNow.return_value + duration - datetime.timedelta(minutes=1)
        await bot.send_reminders(self.bot, self.config)
        assert not mockKeybaseSend.called
        mockNow.return_value = mockNow.return_value + duration + datetime.timedelta(minutes=1)
        await bot.send_reminders(self.bot, self.config)
        mockKeybaseSend.assert_called_with(self.bot, TEST_CONV_ID, ":bell: *Reminder:* " + reminder)

    async def test_snooze_for(self, mockNow, mockRandom, mockKeybaseSend):
        await self.snooze_test(mockNow, mockKeybaseSend, "snooze for 12 minutes",
                         "Ok. I'll remind you again in 12 minutes.", datetime.timedelta(minutes=12))

    # Snooze with a default of 10 minutes when the user doesn't specify a duration.
    async def test_snooze(self, mockNow, mockRandom, mockKeybaseSend):
        await self.snooze_test(mockNow, mockKeybaseSend, "snooze",
                         "Ok. I'll remind you again in 10 minutes.", datetime.timedelta(minutes=10))

    async def test_snooze_nosep(self, mockNow, mockRandom, mockKeybaseSend):
        await self.snooze_test(mockNow, mockKeybaseSend, "snooze 25min",
                         "Ok. I'll remind you again in 25min.", datetime.timedelta(minutes=25))

    async def test_vacuum(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me to foo tomorrow",
                "foo", "on Monday at 9:02 PM",
                "on Monday April 9 2018 at 9:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 0
        await self.reminder_test(
                "remind me to foo tomorrow",
                "foo", "on Tuesday at 9:02 PM",
                "on Tuesday April 10 2018 at 9:02 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 1
        await self.message_test("snooze for 12 minutes",
             "Ok. I'll remind you again in 12 minutes.", mockKeybaseSend)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 0
        mockNow.return_value = mockNow.return_value + datetime.timedelta(minutes=15)
        await bot.send_reminders(self.bot, self.config)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 0
        await self.message_test("remind me to foo tomorrow",
            "Ok! I'll remind you to foo on Wednesday at 9:17 PM", mockKeybaseSend)
        rows = bot.vacuum_old_reminders(self.config)
        assert rows == 1

    async def delete_test(self, delete_text, reminder_text, mockKeybaseSend):
        await self.send_message("remind me to do something else on Tuesday", mockKeybaseSend)
        await self.send_message(reminder_text, mockKeybaseSend)
        await self.send_message(delete_text, mockKeybaseSend)
        assert mockKeybaseSend.call_args[0] != bot.UNKNOWN
        list_output = "Here are your upcoming reminders:\n\n1. do something else - on Tuesday April 10 2018 at 12:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)
        await self.send_message("delete reminder #1", mockKeybaseSend)

    async def test_delete(self, mockNow, mockRandom, mockKeybaseSend):
        reminder = "remind me to foo tomorrow"

        await self.delete_test("delete the foo reminder", reminder, mockKeybaseSend)
        await self.delete_test("delete the reminder to foo", reminder, mockKeybaseSend)
        await self.delete_test("delete the reminder for 9:02pm tomorrow", reminder, mockKeybaseSend)
        await self.delete_test("delete reminder # 1", reminder, mockKeybaseSend)
        await self.delete_test("delete reminder 1", reminder, mockKeybaseSend)

    async def test_delete_response(self, mockNow, mockRandom, mockKeybaseSend):
        await self.send_message("remind me to foo in 1 hour", mockKeybaseSend)
        await self.message_test("delete the foo reminder",
            "Alright, I've deleted the reminder to foo that was set for 10:02 PM.", mockKeybaseSend)

        await self.send_message("remind me to beep on Sunday", mockKeybaseSend)
        await self.message_test("delete the beep reminder",
            "Alright, I've deleted the reminder to beep that was set for Sunday at 12:00 AM.", mockKeybaseSend)

    async def test_delete_undo(self, mockNow, mockRandom, mockKeybaseSend):
        await self.send_message("remind me to foo tomorrow", mockKeybaseSend)
        await self.send_message("delete the foo reminder", mockKeybaseSend)
        await self.message_test("undo", bot.OK, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. foo - on Monday April 9 2018 at 9:02 PM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me every tuesday 8am to eat a quiche",
                "eat a quiche", "every week on Tuesday at 8:00 AM",
                "every week on Tuesday at 8:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every week on Tuesday at 8:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating_preppy(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me on every tuesday at 8am to eat a quiche",
                "eat a quiche", "every week on Tuesday at 8:00 AM",
                "every week on Tuesday at 8:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every week on Tuesday at 8:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating_every_other(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me on every other tuesday to eat a quiche",
                "eat a quiche", "every 2 weeks on Tuesday at 12:00 AM",
                "every 2 weeks on Tuesday at 12:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every 2 weeks on Tuesday at 12:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating_every_other_with_time(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me on every other tuesday at 10am to eat a quiche",
                "eat a quiche", "every 2 weeks on Tuesday at 10:00 AM",
                "every 2 weeks on Tuesday at 10:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every 2 weeks on Tuesday at 10:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating_nth(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me every 6 hours to eat a quiche",
                "eat a quiche", "every 6 hours",
                "every 6 hours",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every 6 hours\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating_snooze(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me every tuesday 8am to eat a quiche",
                "eat a quiche", "every week on Tuesday at 8:00 AM",
                "every week on Tuesday at 8:00 AM",
                datetime.timedelta(days=2),
                mockNow, mockKeybaseSend)
        await self.send_message("snooze for 20 minutes", mockKeybaseSend)

        # snoozed message shows up
        list_output = "Here are your upcoming reminders:\n\n" \
            "1. eat a quiche - on Tuesday April 10 2018 at 9:22 PM\n" \
            "2. eat a quiche - every week on Tuesday at 8:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

        # and the message was snoozed
        mockNow.return_value = mockNow.return_value + datetime.timedelta(minutes=21)
        await bot.send_reminders(self.bot, self.config)
        mockKeybaseSend.assert_called_with(self.bot, TEST_CONV_ID, ":bell: *Reminder:* eat a quiche")

        # and the repetition still happens
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every week on Tuesday at 8:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating_weekday(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me every weekday at 6pm to eat a quiche",
                "eat a quiche", "every weekday at 6:00 PM",
                "every weekday at 6:00 PM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. eat a quiche - every weekday at 6:00 PM\n"
        await self.message_test("list", list_output, mockKeybaseSend)
        # 4 weekdays
        for i in range(4):
            mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
            await bot.send_reminders(self.bot, self.config)
            mockKeybaseSend.assert_called_with(self.bot, TEST_CONV_ID, ":bell: *Reminder:* eat a quiche")

        # saturday
        mockKeybaseSend.reset_mock()
        mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
        await bot.send_reminders(self.bot, self.config)
        assert not mockKeybaseSend.called

        # sunday
        mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
        await bot.send_reminders(self.bot, self.config)
        assert not mockKeybaseSend.called

        # monday
        mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
        await bot.send_reminders(self.bot, self.config)
        mockKeybaseSend.assert_called_with(self.bot, TEST_CONV_ID, ":bell: *Reminder:* eat a quiche")

    async def test_repeating_year(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me every year on january 1 to have a great year",
                "have a great year", "every year on January 1 at 12:00 AM",
                "every year on January 1 at 12:00 AM",
                datetime.timedelta(days=365),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. have a great year - every year on January 1 at 12:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating_month(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me every month on the 30th at 12:00 AM to pay the rent",
                "pay the rent", "every month on the 30th at 12:00 AM",
                "every month on the 30th at 12:00 AM",
                datetime.timedelta(days=30),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. pay the rent - every month on the 30th at 12:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating_week_day(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me every week day at 8am to wake up",
                "wake up", "every weekday at 8:00 AM",
                "every weekday at 8:00 AM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. wake up - every weekday at 8:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    # Bot used to assume 12:00 AM but now asks for clarification on time.
    # The new behavior is better. Test should be udpated.
    @unittest.skip("outdated")
    async def test_repeating_week_day_2(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "remind me every week day to wake up",
                "wake up", "every weekday at 12:00 AM",
                "every weekday at 12:00 AM",
                datetime.timedelta(days=1),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. wake up - every weekday at 12:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

    async def test_repeating_sunday(self, mockNow, mockRandom, mockKeybaseSend):
        await self.reminder_test(
                "Remind me every Sunday at 11am to water the plant",
                "water the plant", "every week on Sunday at 11:00 AM",
                "every week on Sunday at 11:00 AM",
                datetime.timedelta(days=7),
                mockNow, mockKeybaseSend)
        list_output = "Here are your upcoming reminders:\n\n1. water the plant - every week on Sunday at 11:00 AM\n"
        await self.message_test("list", list_output, mockKeybaseSend)

        # 1 more day
        mockKeybaseSend.reset_mock()
        mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
        await bot.send_reminders(self.bot, self.config)
        assert not mockKeybaseSend.called

    # Make sure it doesn't try to send a reminder after more than 10 failures
    async def test_reminder_errors(self, mockNow, mockRandom, mockKeybaseSend):
        await self.message_test(
            "remind me to foo tomorrow", "Ok! I'll remind you to foo on Monday at 9:02 PM",
            mockKeybaseSend,
        )
        mockNow.return_value = mockNow.return_value + datetime.timedelta(days=1)
        mockKeybaseSend.side_effect = Exception("failure to send reminder")
        await bot.send_reminders(self.bot, self.config)
        rs = get_due_reminders(DB, error_limit=0)
        assert len(rs) == 0
        rs = get_due_reminders(DB, error_limit=1)
        assert len(rs) == 1
        id = rs[0].id
        # try more than error_limit (10) times
        for i in range(15):
            await bot.send_reminders(self.bot, self.config)

        r = Reminder.lookup(id, DB)
        assert r.errors == 11


if __name__ == '__main__':
    unittest.main()
