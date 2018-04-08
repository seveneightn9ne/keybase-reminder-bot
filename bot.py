#!/usr/bin/env python

import argparse, configparser, os, pytz, sqlite3, subprocess, sys, time, traceback
from datetime import datetime

import conversation, keybase, parse
from conversation import Conversation

HELP_WHEN = "Sorry, I didn't understand. When should I set the reminder for?" \
        " You can say something like \"tomorrow at 10am\" or \"in 30 minutes\"."
HELP_TIMEZONE = "Sorry, I didn't understand. What's your timezone?" \
        " It can be something like \"ET\", \"PT\", or \"GMT\"."
UNKNOWN = "Sorry, I didn't understand that message."
PROMPT_HELP = "Hey there, I didn't understand that." \
        " Just say \"help\" to see what sort of things I understand."
#HELLO = lambda(name): "Hi " + name + "! To set a reminder just"

def setup():
    try:
        subprocess.check_call(['keybase', 'login', username])
    except subprocess.CalledProcessError:
        print >> sys.stderr, "FATAL: Error during call to `keybase login " + username + "`"
        sys.exit(1)
    try:
        c = sqlite3.connect(db)
    except sqlite3.OperationalError as e:
        print >> sys.stderr, "FATAL: Error connecting to " + db + ": " + e.message
        sys.exit(1)
    c.execute('''create table if not exists reminders (
        reminder_time int,
        created_time int not null,
        body text not null,
        user text not null,
        channel text not null)''')
    c.execute('create index if not exists idx_reminder_time on reminders(reminder_time)')
    c.execute('create index if not exists idx_reminder_user on reminders(user)')
    c.execute('create index if not exists idx_reminder_channel on reminders(channel, reminder_time)')
    c.execute('''create table if not exists users (
        username text not null unique,
        settings text not null)''')
    c.execute('create index if not exists idx_user_name on users(username)')
    c.execute('''create table if not exists conversations (
        channel text not null,
        last_active_time int not null,
        context int not null,
        reminder_rowid int,
        debug boolean not null)''')
    c.execute('create index if not exists idx_conversation_channel on conversations(channel)')
    c.commit()
    print "ReminderBot is running..."

# Returns True iff I interacted with the user.
def process_message(message, conv):
    if not message.is_private_channel() \
            and not username in message.text \
            and conv.context == conversation.CTX_NONE:
        print "Ignoring message not for me"
        return False

    # TODO need some sort of onboarding for first-time user

    msg_type, data = parse.parse_message(message, conv)
    print "Received message parsed as " + str(msg_type)
    if msg_type == parse.MSG_REMINDER and message.user().timezone is None:
        keybase.send(conv.channel, "I'm assuming your timezone is US/Eastern." \
                " If it's not, just tell me something like \"my timezone is US/Pacific\".")
        message.user().set_timezone("US/Eastern")
    if msg_type == parse.MSG_REMINDER:
        reminder = data
        reminder.store()
        if not reminder.reminder_time:
            conv.set_context(conversation.CTX_WHEN, reminder=reminder)
            return keybase.send(conv.channel, "When do you want to be reminded?")
        else:
            return keybase.send(conv.channel, reminder.confirmation())
    elif msg_type == parse.MSG_STFU:
        conv.clear_context()
        return keybase.send(conv.channel, "ok!")
    elif msg_type == parse.MSG_HELP:
        message.user().set_seen_help()
        return keybase.send(conv.channel, HELP)
    elif msg_type == parse.MSG_TIMEZONE:
        message.user().set_timezone(data)
        return keybase.send(conv.channel, "Got it!")
    elif msg_type == parse.MSG_WHEN:
        conv.reminder.set_time(data)
        confirmation = conv.reminder.confirmation()
        conv.set_context(conversation.CTX_NONE)
        return keybase.send(conv.channel, confirmation)
    elif msg_type == parse.MSG_UNKNOWN_TZ:
        return keybase.send(conv.channel, HELP_TZ)
    elif msg_type == parse.MSG_UNKNOWN:
        if conv.context == conversation.CTX_WHEN:
            return keybase.send(conv.channel, HELP_WHEN)
        else: # CTX_NONE
            if conv.last_active_time and \
                (datetime.now(pytz.utc) - conv.last_active_time).seconds < 60 * 30:
                # we're in the middle of a conversation
                return keybase.send(conv.channel, UNKNOWN)
            if not message.is_private_channel():
                # assume you weren't talking to me..
                return False
            if not message.user().has_seen_help:
                return keybase.send(conv.channel, PROMPT_HELP)
            # TODO not sure what to do here. I'll ignore it for now
            return False

    # Shouldn't be able to get here
    print msg_type, data
    assert False

def process_new_messages():
    results = keybase.call("list")
    all_convs = results["conversations"]
    unread_convs = filter(lambda conv: conv["unread"], all_convs)
    print str(len(unread_convs)) + " unread conversations"

    for conv_json in unread_convs:
        channel = conv_json["channel"]["name"]
        #print channel + " is unread"
        conv = Conversation.lookup(channel, db)
        #print conv.channel, " loaded"
        params = {"options": {
                "channel": {"name": channel},
                "unread_only": True}}
        response = keybase.call("read", params)
        #print "other response", response
        for message in response["messages"]:
            # TODO consider processing all messages together
            try:
                if process_message(keybase.Message(message, db), conv):
                    conv.set_active()
            except:
                keybase.send(channel, "Ugh! I crashed! You can complain to @jessk.")
                conv.set_context(conversation.CTX_NONE)
                raise

def send_reminders():
    # TODO
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Beep boop.')
    parser.add_argument('--config', default='default.ini',
                        help='config file')
    parser.add_argument('--wipedb', help='wipe the database before running',
                        action='store_true')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config)

    global db
    db = config['database']['file']

    if args.wipedb:
        os.remove(db)

    global username
    username = config['keybase']['username']

    setup()

    # TODO handle sigterm

    while True:
        try:
            process_new_messages()
        except:
            exc_type, value, tb = sys.exc_info()
            traceback.print_tb(tb)
            print >> sys.stderr, str(exc_type) + ": " + str(value)

        try:
            send_reminders()
        except:
            exc_type, value, tb = sys.exc_info()
            traceback.print_tb(tb)
            print >> sys.stderr, exc_type + ": " + exc_value

        time.sleep(1)

