# Reminders

import random, sqlite3, time
from collections import namedtuple
from datetime import timedelta
from dateutil.relativedelta import *
from pytz import timezone

import util
from user import User

OK = ["Ok!", "Gotcha.", "Sure thing!", "Alright.", "You bet.", "Got it."]

INTERVAL_MINUTE = "minute"
INTERVAL_HOUR = "hour"
INTERVAL_DAY = "day"
INTERVAL_WEEKDAY = "weekday"
INTERVAL_WEEK = "week"
INTERVAL_MONTH = "month"
INTERVAL_YEAR = "year"
INTERVALS = {
    INTERVAL_MINUTE: lambda t,n: t + timedelta(minutes=n),
    INTERVAL_HOUR: lambda t,n: t + timedelta(hours=n),
    INTERVAL_DAY: lambda t,n: t + timedelta(days=n),
    INTERVAL_WEEKDAY: lambda t,n: t + timedelta(days=n + (1 if t.weekday() == 5 else (2 if t.weekday() == 4 else 0))),
    INTERVAL_WEEK: lambda t,n: t + timedelta(days=7*n),
    INTERVAL_MONTH: lambda t,n: t + relativedelta(months=n),
    INTERVAL_YEAR: lambda t,n: t + relativedelta(years=n),
}

Repetition = namedtuple("Repetition", ["interval", "nth"])

class Reminder(object):
    def __init__(self, body, time, repetition, username, conv_id, db):
        # time is a datetime in utc
        self.reminder_time = time
        self.created_time = util.now_utc()
        self.body = body
        self.repetition = repetition if repetition else Repetition(None, None)
        self.username = username
        self.conv_id = conv_id
        self.deleted = False
        self.id = None # when it's from the DB
        self.db = db
        self.errors = 0

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
        repetition = Repetition(row["repetition_interval"], row["repetition_nth"]) if row["repetition_interval"] else None
        reminder = Reminder(row["body"], reminder_time, repetition, row["user"], row["conv_id"], db)
        reminder.created_time = util.from_ts(row["created_time"])
        reminder.id = row["rowid"]
        reminder.deleted = row["deleted"]
        reminder.errors = row["errors"]
        return reminder

    def get_user(self):
        return User.lookup(self.username, self.db)

    def set_time(self, time, repetition):
        assert self.reminder_time is None
        assert self.id is not None
        self.reminder_time = time
        self.repetition = repetition
        with sqlite3.connect(self.db) as c:
            c.execute('update reminders set reminder_time=?, repetition_interval=?, repetition_nth=? where rowid=?',
                    (util.to_ts(time), repetition.interval, repetition.nth, self.id))

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

    def snooze_until(self, t):
        assert self.id is not None
        assert t is not None
        self.deleted = False
        self.reminder_time = t
        self.repetition = Repetition(None, None)
        with sqlite3.connect(self.db) as c:
            c.execute('UPDATE reminders SET deleted=0, reminder_time=?, repetition_interval=?, repetition_nth=? WHERE rowid=?',
                      (util.to_ts(self.reminder_time), None, None, self.id,))

    def increment_error(self):
        assert self.id is not None
        self.errors += 1
        with sqlite3.connect(self.db) as c:
            c.execute('UPDATE reminders SET errors=? WHERE rowid=?', (self.errors, self.id))

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
                deleted,
                repetition_interval,
                repetition_nth,
                errors)
                values (?,?,?,?,?,?,?,?,?)''', (
                reminder_ts,
                created_ts,
                self.body,
                self.username,
                self.conv_id,
                self.deleted,
                self.repetition.interval,
                self.repetition.nth,
                self.errors))
            self.id = cur.lastrowid

    def human_time(self, full=False, preposition=True):
        assert self.reminder_time is not None
        user_tz = self.get_user().timezone
        now = util.now_utc()
        delta = self.reminder_time - now
        # Default timezone to US/Eastern TODO magic string used in a couple places
        tz = timezone(user_tz) if user_tz else timezone('US/Eastern')
        needs_date = full or delta.total_seconds() > 60 * 60 * 16 # today-ish
        needs_day = full or (needs_date and delta.days > 7)
        needs_year = full or (needs_day and self.reminder_time.year != now.year)

        # now consider the repetition
        needs_dow = needs_date and self.repetition.interval in (None, INTERVAL_WEEK)
        needs_day = needs_day and self.repetition.interval in (None, INTERVAL_YEAR, INTERVAL_MONTH)
        needs_month = needs_day and self.repetition.interval != INTERVAL_MONTH
        needs_year = needs_year and not self.repeats() # no repeating intervals state the year
        needs_time = self.repetition.interval not in ("hour", "minute")

        needs_date = any((needs_dow, needs_day, needs_month, needs_year))

        fmt = ""
        if needs_date and preposition:
            fmt += "on "
        if needs_dow:
            fmt += "%A " # on Monday
        if needs_month and needs_day:
            fmt += "%B %-d " # April 10
        if needs_day and not needs_month:
            fmt += "the {S} " # the 10th
        if needs_year:
            fmt += "%Y " # 2018
        if needs_time:
            if needs_date or preposition:
                fmt += "at "
            fmt += "%-I:%M %p" # at 10:30 AM
            if not user_tz:
                fmt += " %Z" # EDT or EST
        # TODO maybe this (or something nearby) will throw pytz.exceptions.AmbiguousTimeError
        # near DST transition?
        local = util.to_local(self.reminder_time, tz)
        formatted_time = util.strftime(fmt, local)
        if self.repeats():
            rp = "every "
            if self.repetition.nth > 1:
                rp += str(self.repetition.nth) + " " + self.repetition.interval + "s"
            else:
                rp += self.repetition.interval

            if self.repetition.interval in ["hour", "minute"]:
                return rp # exclude the "at 9:00 PM" portion
            return rp + " " + formatted_time
        return formatted_time

    def repeats(self):
        return self.repetition.interval != None

    def set_next_reminder(self):
        if not self.repeats():
            return
        new_time = INTERVALS[self.repetition.interval](self.reminder_time, self.repetition.nth)
        # In case the reminder was older than now (maybe bot was offline), make sure the next reminder is in the future:
        while new_time < util.now_utc():
            new_time = INTERVALS[self.repetition.interval](new_time, self.repetition.nth)
        new_reminder = Reminder(self.body, new_time, self.repetition, self.username, self.conv_id, self.db)
        new_reminder.store()

    def confirmation(self):
        return random.choice(OK) + " I'll remind you to " + self.body + " " + self.human_time()

    def reminder_text(self):
        return ":bell: *Reminder:* " + self.body

def get_due_reminders(db, error_limit):
    reminders = []
    now_ts = util.to_ts(util.now_utc())
    with sqlite3.connect(db) as c:
        c.row_factory = sqlite3.Row
        cur = c.cursor()
        cur.execute('SELECT rowid, * FROM reminders WHERE reminder_time<=? AND deleted=0 AND errors<=? LIMIT 100', (now_ts, error_limit))
        for row in cur:
            reminders.append(Reminder.from_row(row, db))
    return reminders
