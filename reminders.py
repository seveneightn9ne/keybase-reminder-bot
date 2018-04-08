# Reminders

import random, sqlite3, time
import datetime
from user import User
from pytz import timezone
import pytz

OK = ["Ok!", "Gotcha." "Sure thing!", "Alright.", "You bet.", "Got it."]

def to_ts(dt):
    return int(time.mktime(dt.timetuple()))

class Reminder(object):
    def __init__(self, body, time, username, channel, db):
        # time is a datetime in utc
        self.reminder_time = time
        self.created_time = datetime.datetime.now(pytz.utc)
        self.body = body
        self.username = username
        self.channel = channel
        self.id = None # when it's from the DB
        self.db = db

    @classmethod
    def lookup(cls, rowid, db):
        with sqlite3.connect(db) as c:
            cur = c.cursor()
            cur.execute(''' select
                body,
                reminder_time,
                user,
                channel,
                created_time from reminders where rowid=?''', (rowid,))
            row = cur.fetchone()
        assert row is not None
        reminder_time = datetime.datetime.fromtimestamp(row[1], tz=pytz.utc) if row[1] else None
        reminder = Reminder(row[0], reminder_time, row[2], row[3], db)
        reminder.created_time = datetime.datetime.fromtimestamp(row[4], tz=pytz.utc)
        reminder.id = rowid
        return reminder

    def get_user(self):
        return User.lookup(self.username, self.db)

    def set_time(self, time):
        assert self.reminder_time is None
        assert self.id is not None
        self.reminder_time = time
        with sqlite3.connect(self.db) as c:
            c.execute('update reminders set reminder_time=? where rowid=?', (time, self.id))

    def delete(self):
        assert self.id is not None
        with sqlite3.connect(self.db) as c:
            c.execute('delete from reminders where rowid=?', (self.id,))

    def store(self):
        reminder_ts = to_ts(self.reminder_time) if self.reminder_time else None
        created_ts = to_ts(self.created_time)
        with sqlite3.connect(self.db) as c:
            cur = c.cursor()
            cur.execute('''insert into reminders (
                reminder_time,
                created_time,
                body,
                user,
                channel)
                values (?,?,?,?,?)''', (
                reminder_ts,
                created_ts,
                self.body,
                self.username,
                self.channel))
            self.id = cur.lastrowid

    def human_time(self):
        assert self.reminder_time is not None
        user_tz = self.get_user().timezone
        now = datetime.datetime.now(pytz.utc)
        delta = self.reminder_time - now
        # Default timezone to US/Eastern TODO magic string used in a couple places
        tz = timezone(user_tz) if user_tz else timezone('US/Eastern')
        needs_date = delta.total_seconds() > 60 * 60 * 16 # today-ish
        needs_day = needs_date and delta.days > 7
        needs_year = needs_day and self.reminder_time.year != now.year
        fmt = ""
        if needs_date:
            fmt += "on %A " # on Monday
            if needs_day:
                fmt += "%B %d " # April 10
            if needs_year:
                fmt += "%Y " # 2018
        fmt += "at %I:%M %p" # at 10:30 AM
        if not user_tz:
            fmt += " %Z" # EDT or EST
        # TODO maybe this (or something nearby) will throw pytz.exceptions.AmbiguousTimeError
        # near DST transition?
        return self.reminder_time.replace(tzinfo=pytz.utc).astimezone(tz).strftime(fmt)

    def confirmation(self):
        return random.choice(OK) + " I'll remind you to " + self.body + " " + self.human_time()

