import datetime
import pytz
import time

def now_utc():
    return datetime.datetime.now(tz=pytz.utc)

def now_local(timezone_str):
    return now_utc().astimezone(pytz.timezone(timezone_str))

def to_local(dt, tz):
    return dt.replace(tzinfo=pytz.utc).astimezone(tz)

def to_ts(dt):
    return (dt - datetime.datetime(1970,1,1, tzinfo=pytz.utc)).total_seconds()

def from_ts(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, tz=pytz.utc)

def timezone_diff(old, new):
    # Returns the number of seconds between the two timezone strings.
    # e.g. timezone_diff('EDT', 'PDT') = 3 * 60 * 60
    #      timezone_diff('PDT', 'EDT') = -3 * 60 * 60
    old_time = now_local(old)
    new_time = old_time.astimezone(pytz.timezone(new))
    return (old_time.utcoffset() - new_time.utcoffset()).total_seconds()

def date_suffix(d):
    return 'th' if 11<=d<=13 else {1:'st',2:'nd',3:'rd'}.get(d%10, 'th')

def strftime(format, t):
    return t.strftime(format).replace('{S}', str(t.day) + date_suffix(t.day))