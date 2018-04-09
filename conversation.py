# Conversations (channels)

import sqlite3, time

import util
from reminders import Reminder

# Contexts
CTX_NONE = 0 # no context
CTX_WHEN = 1 # When should I remind you?
#CTX_TIMEZONE = 2 # What's your timezone?
# TODO count unknown messages to send a help text

class Conversation(object):
    def __init__(self, channel, db):
        self.channel = channel
        self.debug = False
        self.context = 0
        self.reminder_id = None
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
        conv.last_active_time = util.from_ts(row[0])
        #print "Loaded conv last active", conv.last_active_time
        conv.context = row[1]
        conv.reminder_id = row[2]
        conv.debug = row[3]
        return conv

    def get_reminder(self):
        if not self.reminder_id:
            return None
        return Reminder.lookup(self.reminder_id, self.db)

    def get_all_reminders(self):
        reminders = []
        with sqlite3.connect(self.db) as c:
            c.row_factory = sqlite3.Row
            cur = c.cursor()
            cur.execute('''select rowid, * from reminders where channel=? and reminder_time>=?
                    order by reminder_time''',
                    (self.channel, util.to_ts(util.now_utc())))
            for row in cur:
                reminders.append(Reminder.from_row(row, self.db))
        return reminders

    def set_context(self, context, reminder=None):
        assert (not reminder) or reminder.id
        reminder_id = reminder.id if reminder else None
        if context == CTX_NONE:
            assert reminder_id == None
        if context == CTX_WHEN:
            assert reminder_id != None

        self.context = context
        self.reminder_id = reminder_id

        with sqlite3.connect(self.db) as c:
            c.execute('''update conversations set
                context=?, reminder_rowid=? where channel=?''',
                (context, reminder_id, self.channel))

    def clear_context(self):
        if self.reminder_id:
            self.get_reminder().delete()
        self.set_context(CTX_NONE)

    def set_active(self, when=None):
        if when is None:
            when = util.now_utc()
        self.last_active_time = when
        #print "Setting last active time!", self.last_active_time
        with sqlite3.connect(self.db) as c:
            cur = c.cursor()
            cur.execute('update conversations set last_active_time=? where channel=?',
                    (util.to_ts(self.last_active_time), self.channel))
            assert cur.rowcount == 1

    def store(self):
        active_ts = util.to_ts(self.last_active_time) if self.last_active_time else 0
        #print "storing new conv " + self.channel
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
                self.reminder_id,
                self.debug))

    # Delete the conversation from the database, doesn't delete related reminders
    # TODO make sure a reminder can be sent to a conversation that isn't in the DB
    def delete(self):
        with sqlite3.connect(self.db) as c:
            c.execute('delete from conversations where channel=?', (self.channel,))
