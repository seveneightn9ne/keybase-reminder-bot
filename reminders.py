# Reminders

import random, sqlite3, time
from pytz import timezone

import util
from user import User

OK = ["Ok!", "Gotcha.", "Sure thing!", "Alright.", "You bet.", "Got it."]

class Reminder(object):
    def __init__(self, body, time, username, conv_id, db):
        # time is a datetime in utc
        self.reminder_time = time
        self.created_time = util.now_utc()
        self.body = body
        self.username = username
        self.conv_id = conv_id
        self.deleted = False
        self.id = None # when it's from the DB
        self.db = db

    @classmethod
    def lookup(cls, rowid, db):
        with sqlite3.connect(db) as c:
            c.row_factory = sqlite3.Row
            cur = c.cursor()
            cur.execute('select rowid, * from reminders where rowid=?', (rowid,))
            row = cur.fetchone()
        assert row is not None
        return cls.from_row(row, db)

    @classmethod
    def from_row(cls, row, db):
        reminder_time = util.from_ts(row["reminder_time"]) if row["reminder_time"] else None
        reminder = Reminder(row["body"], reminder_time, row["user"], row["conv_id"], db)
        reminder.created_time = util.from_ts(row["created_time"])
        reminder.id = row["rowid"]
        reminder.deleted = row["deleted"]
        return reminder

    def get_user(self):
        return User.lookup(self.username, self.db)

    def set_time(self, time):
        assert self.reminder_time is None
        assert self.id is not None
        self.reminder_time = time
        with sqlite3.connect(self.db) as c:
            c.execute('update reminders set reminder_time=? where rowid=?',
                    (util.to_ts(time), self.id))

    def delete(self):
        self.deleted = True
        assert self.id is not None
        with sqlite3.connect(self.db) as c:
            cur = c.cursor()
            cur.execute('update reminders set deleted=1 where rowid=?', (self.id,))
            assert cur.rowcount == 1

    def undelete(self):
        self.deleted = False
        assert self.id is not None
        with sqlite3.connect(self.db) as c:
            c.execute('update reminders set deleted=0 where rowid=?', (self.id,))

    def permadelete(self):
        assert self.id is not None
        with sqlite3.connect(self.db) as c:
            c.execute('delete from reminders where rowid=?', (self.id,))

    def store(self):
        reminder_ts = util.to_ts(self.reminder_time) if self.reminder_time else None
        created_ts = util.to_ts(self.created_time)
        with sqlite3.connect(self.db) as c:
            cur = c.cursor()
            cur.execute('''insert into reminders (
                reminder_time,
                created_time,
                body,
                user,
                conv_id,
                deleted)
                values (?,?,?,?,?,?)''', (
                reminder_ts,
                created_ts,
                self.body,
                self.username,
                self.conv_id,
                self.deleted))
            self.id = cur.lastrowid

    def human_time(self, full=False):
        assert self.reminder_time is not None
        user_tz = self.get_user().timezone
        now = util.now_utc()
        delta = self.reminder_time - now
        # Default timezone to US/Eastern TODO magic string used in a couple places
        tz = timezone(user_tz) if user_tz else timezone('US/Eastern')
        needs_date = full or delta.total_seconds() > 60 * 60 * 16 # today-ish
        needs_day = full or (needs_date and delta.days > 7)
        needs_year = full or (needs_day and self.reminder_time.year != now.year)
        fmt = ""
        if needs_date:
            fmt += "on %A " # on Monday
            if needs_day:
                fmt += "%B %-d " # April 10
            if needs_year:
                fmt += "%Y " # 2018
        fmt += "at %-I:%M %p" # at 10:30 AM
        if not user_tz:
            fmt += " %Z" # EDT or EST
        # TODO maybe this (or something nearby) will throw pytz.exceptions.AmbiguousTimeError
        # near DST transition?
        local = util.to_local(self.reminder_time, tz)
        return local.strftime(fmt)

    def confirmation(self):
        return random.choice(OK) + " I'll remind you to " + self.body + " " + self.human_time()

    def reminder_text(self):
        return ":bell: *Reminder:* " + self.body

def get_due_reminders(db):
    reminders = []
    now_ts = util.to_ts(util.now_utc())
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        cur = c.cursor()
        cur.execute('select rowid, * from reminders where reminder_time<=? limit 100', (now_ts,))
        for row in cur:
            reminders.append(Reminder.from_row(row, db))
    return reminders
