#!/usr/bin/env python3.8

import argparse, asyncio, configparser, logging, os, pytz, sentry_sdk, signal, sqlite3, sys, time, traceback

from pykeybasebot import Bot
from pykeybasebot.types import chat1

from commands import advertise_commands, clear_command_advertisements
import conversation, database, keybase, parse, reminders, util
from conversation import Conversation

logging.basicConfig(level=logging.INFO)

# Static response messages
HELP_WHEN = "Sorry, I didn't understand. When should I set the reminder for?" \
        " You can say something like \"tomorrow at 10am\" or \"in 30 minutes\"."
HELP_TZ = "Sorry, I couldn't understand your timezone. It can be something like \"US/Pacific\"" \
        " or \"GMT\". If you're stuck, I can use any of the timezones in this list:" \
        " https://stackoverflow.com/questions/13866926/python-pytz-list-of-timezones."\
        " Be sure to get the capitalization right!"
UNKNOWN = "Sorry, I didn't understand that message."
PROMPT_HELP = "Hey there, I didn't understand that." \
        " Just say \"help\" to see what sort of things I understand."
ASSUME_TZ = "I'm assuming your timezone is US/Eastern." \
        " If it's not, just tell me something like \"my timezone is US/Pacific\"."
WHEN = "When do you want to be reminded?"
ACK = "Got it!"
ACK_WHEN = ACK + " " + WHEN
OK = "ok!"
NO_REMINDERS = "You don't have any upcoming reminders."
LIST_INTRO = "Here are your upcoming reminders:\n\n"
SOURCE = "I'm a bot written in python by @jessk.\n"\
         "Source available here: https://github.com/seveneightn9ne/keybase-reminder-bot"
HELP = """*help* _shows this message._
*remind me [when] to [what]* or *remind me to [what] [when]* _set a reminder._
*list* _show upcoming reminders._
*delete the reminder to [what]* / *delete the [when] reminder* / *delete reminder #2* / etc _delete a reminder._
*set my timezone to [tz]* _sets your timezone. This changes when any upcoming reminders will happen._
*#debug* _turns on debug mode -- reports verbose errors including your message text._
*#nodebug* _turns off debug mode._

In general, if I didn't understand, I'll ask for clarification.
If you have any feedback or suggestions, @%s would love to hear them."""
DEBUG = "Thanks! Now I'll log verbose error messages in this conversation. say #nodebug to turn it off."
NODEBUG = "Ok! Debug mode is off now."

# Returns True iff I interacted with the user.
async def process_message_inner(bot, config, message, conv):
    if not message.is_private_channel() \
            and message.bot_username != config.username \
            and not config.username in message.text \
            and not conv.is_strong_context():
        # print("Ignoring message not for me")
        return False

    # TODO need some sort of onboarding for first-time user

    msg_type, data = parse.parse_message(message, conv, config)
    print("Received message parsed as " + str(msg_type) + " in context " + str(conv.context))
    if msg_type == parse.MSG_REMINDER and message.user().timezone is None:
        await keybase.send(bot, conv.id, ASSUME_TZ)
        message.user().set_timezone("US/Eastern")

    if msg_type == parse.MSG_REMINDER:
        reminder = data
        reminder.store()
        if not reminder.reminder_time:
            conv.set_context(conversation.CTX_WHEN, reminder=reminder)
            await keybase.send(bot, conv.id, WHEN)
            return True
        else:
            conv.set_context(conversation.CTX_SET, reminder=reminder)
            await keybase.send(bot, conv.id, reminder.confirmation())
            return True

    elif msg_type == parse.MSG_STFU:
        conv.clear_context()
        await keybase.send(bot, conv.id, OK)
        return True

    elif msg_type == parse.MSG_HELP:
        message.user().set_seen_help()
        conv.clear_weak_context()
        await keybase.send(bot, conv.id, HELP % config.owner)
        return True

    elif msg_type == parse.MSG_TIMEZONE:
        message.user().set_timezone(data)
        if conv.context == conversation.CTX_WHEN:
            await keybase.send(bot, conv.id, ACK_WHEN)
            return True
        conv.clear_weak_context()
        await keybase.send(bot, conv.id, ACK)
        return True

    elif msg_type == parse.MSG_WHEN:
        reminder = conv.get_reminder()
        reminder.set_time(data[0], data[1])
        confirmation = reminder.confirmation()
        conv.set_context(conversation.CTX_SET, reminder=reminder)
        await keybase.send(bot, conv.id, confirmation)
        return True

    elif msg_type == parse.MSG_LIST:
        reminders = conv.get_all_reminders()
        conv.clear_weak_context()
        if not len(reminders):
            await keybase.send(bot, conv.id, NO_REMINDERS)
            return True
        response = LIST_INTRO
        for i, reminder in enumerate(reminders, start=1):
            response += str(i) + ". " + reminder.body + " - " + reminder.human_time(full=True) + "\n"
        await keybase.send(bot, conv.id, response)
        return True

    elif msg_type == parse.MSG_UNDO:
        if conv.context == conversation.CTX_SET:
            conv.get_reminder().delete()
        elif conv.context == conversation.CTX_DELETED:
            conv.get_reminder().undelete()
        conv.clear_weak_context()
        await keybase.send(bot, conv.id, OK)
        return True

    elif msg_type == parse.MSG_SOURCE:
        conv.clear_weak_context()
        await keybase.send(bot, conv.id, SOURCE)
        return True

    elif msg_type == parse.MSG_UNKNOWN_TZ:
        conv.clear_weak_context()
        await keybase.send(bot, conv.id, HELP_TZ)
        return True

    elif msg_type == parse.MSG_ACK:
        conv.clear_weak_context()
        return True

    elif msg_type == parse.MSG_GREETING:
        conv.clear_weak_context()
        await keybase.send(bot, conv.id, data)
        return True

    elif msg_type == parse.MSG_DEBUG:
        conv.set_debug(True)
        await keybase.send(bot, conv.id, DEBUG)
        return True

    elif msg_type == parse.MSG_NODEBUG:
        conv.set_debug(False)
        await keybase.send(bot, conv.id, NODEBUG)
        return True

    elif msg_type == parse.MSG_DELETE:
        reminder = data
        reminder.delete()
        conv.set_context(conversation.CTX_DELETED, reminder)
        msg = "Alright, I've deleted the reminder to " + reminder.body + " that was set for " + \
            reminder.human_time(preposition=False) + "."
        await keybase.send(bot, conv.id, msg)
        return True

    elif msg_type == parse.MSG_SNOOZE:
        if conv.context != conversation.CTX_REMINDED:
            await keybase.send(bot, conv.id, "Not sure what to snooze.")
            return True
        conv.get_reminder().snooze_until(data.time)
        conv.set_context(conversation.CTX_SET, conv.get_reminder())
        await keybase.send(bot, conv.id, "Ok. I'll remind you again in " + data.phrase + ".")
        return True

    elif msg_type == parse.MSG_UNKNOWN:
        # I don't think an unknown message should clear context at all
        #conv.clear_weak_context()
        await keybase.debug(bot, conv, "Message from @" + message.user().name + " parsed UNKNOWN: " \
                + message.text, config)
        if conv.context == conversation.CTX_WHEN:
            await keybase.send(bot, conv.id, HELP_WHEN)
            return True
        else: # CTX_NONE/weak
            if conv.is_recently_active() or message.user().has_seen_help:
                await keybase.send(bot, conv.id, UNKNOWN)
                return True
            await keybase.send(bot, conv.id, PROMPT_HELP)
            return True

    # Shouldn't be able to get here
    print(msg_type, data)
    assert False, "unexpected parsed msg_type"

async def process_message(bot, config, message, conv):
    active = await process_message_inner(bot, config, message, conv)
    if active:
        conv.set_active()

def get_conv(event, config):
    if event.conv:
        return Conversation.lookup_or_convsummary(event.conv.id, event.conv, config.db)
    if event.msg:
        if not event.msg.conv_id:
            raise RuntimeError("KbEvent msg has no conv_id")
        if event.msg.channel:
            return Conversation.lookup_or_convsummary(event.msg.conv_id, event.msg, config.db)
        return Conversation.lookup(event.msg.conv_id)
    raise RuntimeError("KbEvent has no conv or msg")

class Handler:
    def __init__(self, config):
        self.config = config
    async def __call__(self, bot, event):
        config = self.config
        with sentry_sdk.push_scope() as scope:
            try:
                conv = get_conv(event, config)
                scope.set_tag("conv_id", conv.id)

                if conv.channel == config.debug_team:
                    # Don't do anything in the debug team
                    print("Ignoring message in debug team")
                    return

                if event.error:
                    if event.error == "Unable to decrypt chat message: message not available":
                        return
                    try:
                        raise Exception("Reading message: {}".format(event.error))
                    except:
                        if not config.sentry_dsn:
                            raise
                        # doing it this way gets the stacktrace
                        sentry_sdk.capture_exception()
                        return

                if event.msg.content.type_name != chat1.MessageTypeStrings.TEXT.value:
                    # Ignore messages like edits and people joining the channel
                    print("Ignoring non text message :  " + str(event.msg.content.type_name))
                    return

                if event.msg.sender.username == config.username:
                    # Don't process my own messaages
                    return

                scope.set_user({"username": event.msg.sender.username})

                try:
                    kb_msg = keybase.Message.from_msgsummary(event.msg, config.db)
                    await process_message(bot, config, kb_msg, conv)
                except Exception as e:
                    if hasattr(e, 'message') and e.message.startswith("user is not in conversation:  uid: "):
                        # above error happens when bot doesn't have write permission in the conv
                        # it can be ignored
                        # TODO: suppose you could DM the person who sent you the message to let them know
                        return
                    if not config.sentry_dsn:
                        raise
                    sentry_sdk.capture_exception()
                    try:
                        await keybase.send(bot, conv.id,
                            "Ugh! I crashed! I sent the error to @" + config.owner + " to fix.")
                    except:
                        # Can happen because the original exception is that you can't send to the channel
                        # this is just best-effort, anyway
                        print("Ignoring error in keybase send during crash report")
                    if conv.debug:
                        text = event.msg.content.text.body
                        from_u = event.msg.sender.username
                        print("Error processing message: {}".format(e.message))
                        print("The message, sent by @" + from_u + " was: " + text, config)
                    conv.set_context(conversation.CTX_NONE)
                    return
            except:
                if not config.sentry_dsn:
                    raise
                sentry_sdk.capture_exception()

async def send_reminders(bot, config):
    for reminder in reminders.get_due_reminders(config.db, error_limit=10):
        with sentry_sdk.push_scope() as scope:
            scope.user = {"username": reminder.username}
            scope.set_tag("conv_id", reminder.conv_id)
            try:
                conv = Conversation.lookup(reminder.conv_id, config.db)
                await keybase.send(bot, conv.id, reminder.reminder_text())
                print("sent a reminder for", reminder.reminder_time)
                reminder.set_next_reminder() # if it repeats
                reminder.delete()
                conv.set_active()
                conv.set_context(conversation.CTX_REMINDED, reminder)
            except Exception as e:
                reminder.increment_error()
                if str(e) == "no conversations matched \"{}\"".format(reminder.conv_id):
                    # reminderbot has been removed from the channel. Known error, no need to report
                    continue
                sentry_sdk.capture_exception()

def vacuum_old_reminders(config):
    with sqlite3.connect(config.db) as c:
        cur = c.cursor()
        cur.execute('''DELETE FROM reminders WHERE rowid IN (
            SELECT reminders.rowid FROM reminders
            INNER JOIN conversations ON reminders.conv_id = conversations.id
            WHERE conversations.reminder_rowid != reminders.rowid
            AND reminders.deleted = 1
        )''')
        rows = cur.rowcount
        if rows > 0:
            print("deleted", rows, "old reminders")
    return rows

class Config(object):
    def __init__(self, db, username, owner, debug_team=None, debug_topic=None, autosend_logs=False, sentry_dsn=None):
        self.db = db
        self.username = username
        self.owner = owner
        self.debug_team = debug_team
        self.debug_topic = debug_topic
        self.autosend_logs = autosend_logs
        self.sentry_dsn = sentry_dsn

    @classmethod
    def fromFile(cls, configFile):
        config = configparser.ConfigParser()
        config.read(configFile)
        db = config['database']['file']
        username = config['keybase']['username']
        owner = config['keybase']['owner']
        debug_team = config['keybase'].get('debug_team', None)
        debug_topic = config['keybase'].get('debug_topic', None)
        autosend_logs = config['keybase'].getboolean('autosend_logs', False)
        sentry_dsn = config['sentry'].get('dsn', None)
        return Config(db, username, owner, debug_team, debug_topic, autosend_logs, sentry_dsn)

def setup(config):
    if config.sentry_dsn:
        sentry_sdk.init(config.sentry_dsn)
    database.setup(config.db)
    import nltk
    libs = ('punkt', 'averaged_perceptron_tagger', 'universal_tagset')
    for lib in libs:
        nltk.download(lib, quiet=True)

    return Bot(username=config.username, handler=Handler(config))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Beep boop.')
    parser.add_argument('--config', default='default.ini',
                        help='config file')
    parser.add_argument('--wipedb', help='wipe the database before running',
                        action='store_true')
    args = parser.parse_args()

    config = Config.fromFile(args.config)

    if args.wipedb:
        try:
            os.remove(config.db)
        except OSError:
            pass # it doesn't exist

    bot = setup(config)

    print("ReminderBot is running...")
    print("username: " + config.username)

    loop = asyncio.get_event_loop()

    running = True
    async def signal_handler():
        global running
        running = False
        await clear_command_advertisements(bot)
        loop.stop()

    loop.add_signal_handler(signal.SIGINT, lambda: asyncio.ensure_future(signal_handler()))
    loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.ensure_future(signal_handler()))

    async def listen_loop():
        await advertise_commands(bot)
        await bot.start({})

    async def send_reminder_loop():
        while running:
            sys.stdout.flush()
            sys.stderr.flush()

            try:
                await send_reminders(bot, config)
                vacuum_old_reminders(bot, config)
            except:
                sentry_sdk.capture_exception()

            if not running:
                break

            await asyncio.sleep(1)

    loop.run_until_complete(
        asyncio.gather(listen_loop(), send_reminder_loop()),
    )

    print("ReminderBot shut down gracefully.")
