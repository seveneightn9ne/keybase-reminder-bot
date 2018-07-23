import sqlite3
import sys

import keybase

def initial_tables(c):
    c.execute('''create table if not exists reminders (
        reminder_time int,
        created_time int not null,
        body text not null,
        user text not null,
        conv_id text not null)''')
    c.execute('create index if not exists idx_reminder_time on reminders(reminder_time)')
    c.execute('create index if not exists idx_reminder_conv on reminders(conv_id, reminder_time)')
    c.execute('''create table if not exists users (
        username text not null unique,
        settings text not null)''')
    c.execute('create index if not exists idx_user_name on users(username)')
    c.execute('''create table if not exists conversations (
        id text not null,
        channel text not null,
        is_team boolean not null,
        topic text,
        last_active_time int not null,
        context int not null,
        reminder_rowid int,
        debug boolean not null)''')
    c.execute('create unique index if not exists idx_conversations_id on conversations(id)')

def add_reminder_deleted(c):
    c.execute('alter table reminders add deleted boolean not null default 0')

def add_reminder_repeating(c):
    c.execute('alter table reminders add repetition_interval text')
    c.execute('alter table reminders add repetition_nth int')

def setup(db):
    try:
        c = sqlite3.connect(db)
    except sqlite3.OperationalError as e:
        print >> sys.stderr, "FATAL: Error connecting to " + db + ": " + e.message
        sys.exit(1)

    cur = c.cursor()
    cur.execute('pragma user_version')
    db_version = cur.fetchone()[0]

    migrations = [
            initial_tables,
            add_reminder_deleted,
            add_reminder_repeating,
        ]
    for i, migration in enumerate(migrations, start=1):
        if db_version < i:
            migration(cur)

    cur.execute('pragma user_version = ' + str(len(migrations)))
    c.commit()

