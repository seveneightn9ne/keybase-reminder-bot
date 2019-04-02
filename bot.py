#!/usr/bin/env python

import argparse, configparser, os, pytz, signal, sqlite3, subprocess, sys, time, traceback

import conversation, database, keybase, parse, reminders, util
from conversation import Conversation

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
def process_message_inner(config, message, conv):
    if not message.is_private_channel() \
            and not config.username in message.text \
            and not conv.is_strong_context():
        print "Ignoring message not for me"
        return False, None

    # TODO need some sort of onboarding for first-time user

    msg_type, data = parse.parse_message(message, conv, config)
    print "Received message parsed as " + str(msg_type) + " in context " + str(conv.context)
    if msg_type == parse.MSG_REMINDER and message.user().timezone is None:
        keybase.send(conv.id, ASSUME_TZ)
        message.user().set_timezone("US/Eastern")

    if msg_type == parse.MSG_REMINDER:
        reminder = data
        reminder.store()
        if not reminder.reminder_time:
            conv.set_context(conversation.CTX_WHEN, reminder=reminder)
            return keybase.send(conv.id, WHEN)
        else:
            conv.set_context(conversation.CTX_SET, reminder=reminder)
            return keybase.send(conv.id, reminder.confirmation())

    elif msg_type == parse.MSG_STFU:
        conv.clear_context()
        return keybase.send(conv.id, OK)

    elif msg_type == parse.MSG_HELP:
        message.user().set_seen_help()
        conv.clear_weak_context()
        return keybase.send(conv.id, HELP % config.owner)

    elif msg_type == parse.MSG_TIMEZONE:
        message.user().set_timezone(data)
        if conv.context == conversation.CTX_WHEN:
            return keybase.send(conv.id, ACK_WHEN)
        conv.clear_weak_context()
        return keybase.send(conv.id, ACK)

    elif msg_type == parse.MSG_WHEN:
        reminder = conv.get_reminder()
        reminder.set_time(data[0], data[1])
        confirmation = reminder.confirmation()
        conv.set_context(conversation.CTX_SET, reminder=reminder)
        return keybase.send(conv.id, confirmation)

    elif msg_type == parse.MSG_LIST:
        reminders = conv.get_all_reminders()
        conv.clear_weak_context()
        if not len(reminders):
            return keybase.send(conv.id, NO_REMINDERS)
        response = LIST_INTRO
        for i, reminder in enumerate(reminders, start=1):
            response += str(i) + ". " + reminder.body + " - " + reminder.human_time(full=True) + "\n"
        return keybase.send(conv.id, response)

    elif msg_type == parse.MSG_UNDO:
        if conv.context == conversation.CTX_SET:
            conv.get_reminder().delete()
        elif conv.context == conversation.CTX_DELETED:
            conv.get_reminder().undelete()
        conv.clear_weak_context()
        return keybase.send(conv.id, OK)

    elif msg_type == parse.MSG_SOURCE:
        conv.clear_weak_context()
        return keybase.send(conv.id, SOURCE)

    elif msg_type == parse.MSG_UNKNOWN_TZ:
        conv.clear_weak_context()
        return keybase.send(conv.id, HELP_TZ)

    elif msg_type == parse.MSG_ACK:
        conv.clear_weak_context()
        return True, None

    elif msg_type == parse.MSG_GREETING:
        conv.clear_weak_context()
        return keybase.send(conv.id, data)

    elif msg_type == parse.MSG_DEBUG:
        conv.set_debug(True)
        return keybase.send(conv.id, DEBUG)

    elif msg_type == parse.MSG_NODEBUG:
        conv.set_debug(False)
        return keybase.send(conv.id, NODEBUG)

    elif msg_type == parse.MSG_DELETE:
        reminder = data
        reminder.delete()
        conv.set_context(conversation.CTX_DELETED, reminder)
        msg = "Alright, I've deleted the reminder to " + reminder.body + " that was set for " + \
            reminder.human_time(preposition=False) + "."
        return keybase.send(conv.id, msg)

    elif msg_type == parse.MSG_SNOOZE:
        if conv.context != conversation.CTX_REMINDED:
            return keybase.send(conv.id, "Not sure what to snooze.")
        conv.get_reminder().snooze_until(data.time)
        conv.set_context(conversation.CTX_SET, conv.get_reminder())
        return keybase.send(conv.id, "Ok. I'll remind you again in " + data.phrase + ".")

    elif msg_type == parse.MSG_UNKNOWN:
        # I don't think an unknown message should clear context at all
        #conv.clear_weak_context()
        if conv.debug:
            keybase.debug("Message from @" + message.user().name + " parsed UNKNOWN: " \
                    + message.text, config)
        if conv.context == conversation.CTX_WHEN:
            return True, HELP_WHEN
        else: # CTX_NONE/weak
            if conv.is_recently_active() or message.user().has_seen_help:
                return True, UNKNOWN
            return True, PROMPT_HELP

    # Shouldn't be able to get here
    print msg_type, data
    assert False, "unexpected parsed msg_type"

def process_message(config, message, conv):
    active, unknown_msg = process_message_inner(config, message, conv)
    if active:
        conv.set_active()
    return unknown_msg

def process_new_messages(config):
    params = {"options": {
        "unread_only": True}}
    results = keybase.call("list", params)
    all_convs = results["conversations"]

    if not all_convs:
        return

    unread_convs = filter(lambda conv: conv["unread"], all_convs)
    # print str(len(unread_convs)) + " unread conversations"

    for conv_json in unread_convs:
        id = conv_json["id"]
        conv = Conversation.lookup(id, conv_json, config.db)
        if conv.channel == config.debug_team:
            # Don't do anything in the debug team
            continue
        params = {"options": {
                "channel": conv_json["channel"],
                "unread_only": True}}
        response = keybase.call("read", params)
        #print "other response", response
        sent_resp = False
        resp_to_send = None
        for message in reversed(response["messages"]):
            if "error" in message:
                print "message error: {}".format(message["error"])
                continue
            # TODO consider processing all messages together
            if not "text" in message["msg"]["content"]:
                # Ignore messages like edits and people joining the channel
                print "ignoring message of type: {}".format(message["msg"]["content"]["type"])
                continue
            try:
                resp = process_message(config, keybase.Message(id, message, config.db), conv)
                if resp is None:
                    sent_resp = True
                elif resp_to_send is None:
                    resp_to_send = resp
            except Exception as e:
                keybase.send(id,
                        "Ugh! I crashed! I sent the error to @" + config.owner + " to fix.")
                keybase.debug("I crashed! Stacktrace:\n" + traceback.format_exc(e), config)
                if conv.debug:
                    text = message["msg"]["content"]["text"]["body"]
                    from_u = message["msg"]["sender"]["username"]
                    keybase.debug("The message, sent by @" + from_u + " was: " + text, config)
                conv.set_context(conversation.CTX_NONE)
                raise e
        if not sent_resp and resp_to_send is not None:
            keybase.send(conv.id, resp_to_send)

def send_reminders(config):
    for reminder in reminders.get_due_reminders(config.db):
        try:
            conv = Conversation.lookup(reminder.conv_id, None, config.db)
            keybase.send(conv.id, reminder.reminder_text())
            print "sent a reminder for", reminder.reminder_time
            reminder.set_next_reminder() # if it repeats
            reminder.delete()
            conv.set_active()
            conv.set_context(conversation.CTX_REMINDED, reminder)
        except Exception as e:
            keybase.debug("I crashed! Stacktrace:\n" + traceback.format_exc(e), config)
            raise e

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
            print "deleted", rows, "old reminders"
    return rows

class Config(object):
    def __init__(self, db, username, owner, debug_team=None, debug_topic=None):
        self.db = db
        self.username = username
        self.owner = owner
        self.debug_team = debug_team
        self.debug_topic = debug_topic

    @classmethod
    def fromFile(cls, configFile):
        config = configparser.ConfigParser()
        config.read(configFile)
        db = config['database']['file']
        username = config['keybase']['username']
        owner = config['keybase']['owner']
        debug_team = config['keybase'].get('debug_team', None)
        debug_topic = config['keybase'].get('debug_topic', None)
        return Config(db, username, owner, debug_team, debug_topic)

def setup(config):
    keybase.setup(config)
    database.setup(config.db)
    import nltk
    libs = ('punkt', 'averaged_perceptron_tagger', 'universal_tagset')
    for lib in libs:
        nltk.download(lib, quiet=True)

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

    setup(config)

    print "ReminderBot is running..."
    print "username: " + config.username

    running = True
    def signal_handler(signal, frame):
        global running
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    while running:
        sys.stdout.flush()
        sys.stderr.flush()

        for task in (
            process_new_messages,
            send_reminders,
            vacuum_old_reminders):
            try:
                task(config)
            except:
                exc_type, value, tb = sys.exc_info()
                traceback.print_tb(tb)
                print >> sys.stderr, str(exc_type) + ": " + str(value)

            if not running:
                break

        time.sleep(1)

    print "ReminderBot shut down gracefully."



