# Conversations (channels)

import sqlite3, time
from reminders import Reminder
from datetime import datetime
import pytz

# Contexts
CTX_NONE = 0 # no context
CTX_WHEN = 1 # When should I remind you?
#CTX_TIMEZONE = 2 # What's your timezone?
# TODO count unknown messages to send a help text

def to_ts(dt):
    return int(time.mktime(dt.timetuple()))

class Conversation(object):
    def __init__(self, channel, db):
        self.channel = channel
        self.debug = False
        self.context = 0
        self.reminder = None
        self.last_active_time = None
        self.db = db

    @classmethod
    def lookup(cls, channel, db):
        conv = Conversation(channel, db)
        with sqlite3.connect(db) as c:
            cur = c.cursor()
            cur.execute('''select
                last_active_time,
                context,
                reminder_rowid,
                debug from conversations where channel=?''', (channel,))
            row = cur.fetchone()
        if row is None:
            conv.store()
            return conv
        conv.last_active_time = datetime.fromtimestamp(row[0], tz=pytz.utc)
        print "Loaded conv last active", conv.last_active_time
        conv.context = row[1]
        if row[2]:
            conv.reminder = Reminder.lookup(row[2], db)
        conv.debug = row[3]
        return conv

    def set_context(self, context, reminder=None):
        assert (not reminder) or reminder.id
        if context == CTX_NONE:
            assert reminder == None
        if context == CTX_WHEN:
            assert reminder != None

        self.context = context
        self.reminder = reminder

        reminder_id = reminder.id if reminder else None
        with sqlite3.connect(self.db) as c:
            c.execute('''update conversations set
                context=?, reminder_rowid=? where channel=?''',
                (context, reminder_id, self.channel))

    def clear_context(self):
        if self.reminder:
            self.reminder.delete()
        self.set_context(CTX_NONE)

    def set_active(self):
        self.last_active_time = datetime.now(pytz.utc)
        #print "Setting last active time!", self.last_active_time
        with sqlite3.connect(self.db) as c:
            cur = c.cursor()
            cur.execute('update conversations set last_active_time=? where channel=?',
                    (to_ts(self.last_active_time), self.channel))
            assert cur.rowcount == 1

    def store(self):
        active_ts = to_ts(self.last_active_time) if self.last_active_time else 0
        print "storing new conv " + self.channel
        with sqlite3.connect(self.db) as c:
            c.execute('''insert into conversations (
                channel,
                last_active_time,
                context,
                reminder_rowid,
                debug) values (?,?,?,?,?)''', (
                self.channel,
                active_ts,
                self.context,
                self.reminder.id if self.reminder else None,
                self.debug))
