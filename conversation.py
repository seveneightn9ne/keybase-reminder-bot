# Conversations (channels)

import sqlite3, time

import util
from reminders import Reminder

# Contexts
CTX_NONE = 0 # no context
CTX_WHEN = 1 # When should I remind you?
CTX_REMINDED = 2 # I've just sent you a reminder.
CTX_SET = 3 # You just finished setting a reminder.
CTX_DELETED = 4 # You just deleted a reminder.
#CTX_TIMEZONE = 2 # What's your timezone?
# TODO count unknown messages to send a help text

class Conversation(object):
    def __init__(self, id, db):
        self.id = id
        self.channel = None
        self.topic = None
        self.is_team = False
        self.debug = False
        self.context = 0
        self.reminder_id = None
        self.last_active_time = None
        self.db = db

    @classmethod
    def lookup(cls, id, conv_json, db):
        conv = Conversation(id, db)
        with sqlite3.connect(db) as c:
            cur = c.cursor()
            cur.execute('''select
                last_active_time,
                context,
                reminder_rowid,
                debug,
                channel,
                is_team,
                topic from conversations where id=?''', (id,))
            row = cur.fetchone()
        if row is None:
            assert conv_json is not None
            conv.channel = conv_json["channel"]["name"]
            conv.is_team = conv_json["channel"]["members_type"] == "team"
            conv.topic = conv_json["channel"]["topic_name"] \
                    if "topic_name" in conv_json["channel"] else None
            conv.store()
            return conv
        conv.last_active_time = util.from_ts(row[0])
        #print "Loaded conv last active", conv.last_active_time
        conv.context = row[1]
        conv.reminder_id = row[2]
        conv.debug = row[3]
        conv.channel = row[4]
        conv.is_team = row[5]
        conv.topic = row[6]
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
            cur.execute('''select rowid, * from reminders where conv_id=?
                    and reminder_time>=?
                    and deleted=0
                    order by reminder_time''',
                    (self.id, util.to_ts(util.now_utc())))
            for row in cur:
                reminders.append(Reminder.from_row(row, self.db))
        return reminders

    def is_recently_active(self):
        MINUTES = 30
        return self.last_active_time and \
                (util.now_utc() - self.last_active_time).total_seconds() < 60 * MINUTES

    # A context where the bot will engage with you until you answer correctly.
    def is_strong_context(self):
        return self.context == CTX_WHEN

    def expects_ack(self):
        return self.is_recently_active() and self.context in (CTX_REMINDED, CTX_SET, CTX_DELETED)

    def set_context(self, context, reminder=None):
        assert (not reminder) or reminder.id
        reminder_id = reminder.id if reminder else None
        if context in (CTX_NONE, CTX_DELETED):
            # In CTX_REMINDED, the reminder has been deleted already.
            assert reminder_id == None
        if context in (CTX_WHEN, CTX_SET, CTX_REMINDED):
            assert reminder_id != None

        self.context = context
        self.reminder_id = reminder_id

        with sqlite3.connect(self.db) as c:
            c.execute('''update conversations set
                context=?, reminder_rowid=? where id=?''',
                (context, reminder_id, self.id))

    def clear_context(self):
        if self.context == CTX_WHEN and self.reminder_id:
            self.get_reminder().delete()
        self.set_context(CTX_NONE)

    def clear_weak_context(self):
        if self.context in (CTX_SET, CTX_REMINDED, CTX_DELETED):
            self.set_context(CTX_NONE)

    def set_active(self, when=None):
        if when is None:
            when = util.now_utc()
        self.last_active_time = when
        #print "Setting last active time!", self.last_active_time
        with sqlite3.connect(self.db) as c:
            cur = c.cursor()
            cur.execute('update conversations set last_active_time=? where id=?',
                    (util.to_ts(self.last_active_time), self.id))
            assert cur.rowcount == 1

    def set_debug(self, val=True):
        self.debug = val
        with sqlite3.connect(self.db) as c:
            c.execute('update conversations set debug=? where id=?', (val, self.id))

    def store(self):
        active_ts = util.to_ts(self.last_active_time) if self.last_active_time else 0
        #print "storing new conv " + self.channel
        with sqlite3.connect(self.db) as c:
            c.execute('''insert into conversations (
                id,
                channel,
                last_active_time,
                context,
                reminder_rowid,
                debug,
                is_team,
                topic) values (?,?,?,?,?,?,?,?)''', (
                self.id,
                self.channel,
                active_ts,
                self.context,
                self.reminder_id,
                self.debug,
                self.is_team,
                self.topic))

    # Delete the conversation from the database, doesn't delete related reminders
    # TODO make sure a reminder can be sent to a conversation that isn't in the DB
    def delete(self):
        with sqlite3.connect(self.db) as c:
            c.execute('delete from conversations where id=?', (self.id,))
