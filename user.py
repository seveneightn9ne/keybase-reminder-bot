# The User

import json, sqlite3
from datetime import datetime
from pytz import timezone

def timezone_diff(old, new):
    # Returns the number of seconds between the two timezone strings.
    # e.g. timezone_diff('EDT', 'PDT') = 3 * 60 * 60
    # remind me at 3:00 (assumed EDT)
    # store as 7:00 UTC
    # set tz to PDT
    # modify 7:00 UTC to 10:00 UTC
    # add 3 hours
    ref = datetime.utcnow()
    old_time = ref.replace(tzinfo=timezone(old))
    new_time = ref.replace(tzinfo=timezone(new))
    delta = new_time - old_time
    seconds = delta.total_seconds()
    if delta.days == -1:
        seconds = -1 * ((60*60*24) - seconds)
    return seconds


class User(object):
    def __init__(self, name, timezone, db):
        self.name = name
        self.timezone = timezone
        self.has_seen_help = False
        self.db = db

    @classmethod
    def lookup(cls, name, db):
        with sqlite3.connect(db) as c:
            cur = c.cursor()
            cur.execute('select username, settings from users where username=?', (name,))
            row = cur.fetchone()
        if row is None:
            user = User(name, None, db)
            user.store()
            return user
        settings = json.loads(row[1])
        user = User(name, settings['timezone'], db)
        if 'has_seen_help' in settings:
            user.has_seen_help = settings['has_seen_help']
        return user

    def set_timezone(self, timezone):
        prev_timezone = self.timezone
        self.timezone = timezone
        # update timezone of all future reminders
        with sqlite3.connect(self.db) as c:
            self.save_settings_inner(c) # transactional with the reminders update
            # TODO do we also want to update created time..?
            if prev_timezone:
                diff = timezone_diff(prev_timezone, timezone)
                c.execute('''update reminders set reminder_time=(reminder_time + ?)
                    where user=? and reminder_time not null''', (diff, self.name))


    def set_seen_help(self):
        self.has_seen_help = True
        self.save_settings()

    def store(self):
        with sqlite3.connect(self.db) as c:
            c.execute('insert into users(username, settings) values (?,?)',
                    (self.name, self.settings_json()))

    def save_settings(self):
        with sqlite3.connect(self.db) as c:
            self.save_settings_inner(c)

    def save_settings_inner(self, c):
        c.execute('update users set settings=? where username=?',
                (self.settings_json(), self.name))

    def settings_json(self):
        return json.dumps({
            'timezone': self.timezone,
            'has_seen_help': self.has_seen_help,
        })

    # Delete the user AND all their reminders
    def delete(self):
        with sqlite3.connect(self.db) as c:
            c.execute('delete from users where username=?', (self.name,))
            c.execute('delete from reminders where user=?', (self.name,))
