# Reminders

import random, sqlite3, time
from datetime import datetime
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
        self.created_time = datetime.now(pytz.utc)
        self.body = body
        self.user = User.lookup(username, db)
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
        reminder_time = datetime.fromtimestamp(row[1], tz=pytz.utc) if row[1] else None
        reminder = Reminder(row[0], reminder_time, row[2], row[3], db)
        reminder.created_time = datetime.fromtimestamp(row[4], tz=pytz.utc)
        reminder.id = rowid
        return reminder

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
                self.user.name,
                self.channel))
            self.id = cur.lastrowid

    def human_time(self):
        assert self.reminder_time is not None
        now = datetime.now(pytz.utc)
        delta = self.reminder_time - now
        # Default timezone to ET
        tz = timezone(self.user.timezone) if self.user.timezone else timezone('ET')
        needs_date = delta.seconds > 60 * 60 * 16 # today-ish
        needs_day = needs_date and delta.days < 7
        needs_year = needs_day and self.reminder_time.year != now.year
        fmt = ""
        if needs_date:
            fmt += "on %A " # on Monday
            if needs_day:
                fmt += "%B %d " # April 10
            if needs_year:
                fmt += "%Y " # 2018
        fmt += "at %I:%M %p" # at 10:30 AM
        if not self.user.timezone:
            fmt += " %Z" # ET
        # TODO maybe this (or something nearby) will throw pytz.exceptions.AmbiguousTimeError
        # near DST transition?
        return self.reminder_time.replace(tzinfo=pytz.utc).astimezone(tz).strftime(fmt)

    def confirmation(self):
        return random.choice(OK) + " I'll remind you " + self.body + " " + self.human_time()

