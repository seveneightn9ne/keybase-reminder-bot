# Parsing messages

import dateparser, pytz, re

import conversation, util
from reminders import Reminder
from user import User
from datetime import datetime # don't use anything that uses now.

MSG_UNKNOWN = 0
MSG_REMINDER = 1
MSG_HELP = 2
MSG_WHEN = 3
MSG_TIMEZONE = 4
MSG_STFU = 5
MSG_UNKNOWN_TZ = 6
MSG_LIST = 7
MSG_SOURCE = 8
MSG_ACK = 9
MSG_GREETING = 10
MSG_UNDO = 11
# TODO MSG_SNOOZE
# TODO MSG_CANCEL

def try_parse_when(when, user):

    def fixup_times(when_str, relative_base):
        # When there is no explicit AM/PM assume the next upcoming one
        # HH:(MM)? (AM|PM)?
        time_regex = regex('(?:[^\w]|^)(\d\d?(:\d\d)?)\s?([ap]\.?m.?)?')
        results = re.findall(time_regex, when_str)
        times = [(m[0], m[1]) for m in results if m[2] == '']
        if len(times) != 1:
            # I don't expect to find more than one time. Rather not do anything.
            return when_str

        time_to_replace, minutes = times[0]
        for fmt in ('%I', '%I:%M'):
            try:
                time = datetime.strptime(time_to_replace, fmt)
                break
            except ValueError:
                pass
        else:
            return when_str # Couldn't parse a time

        if time.hour > 12:
            return # you explicitly are after noon

        if relative_base.hour > time.hour:
            new_hour = str(time.hour + 12)
            return when_str.replace(time_to_replace, new_hour + minutes)

    # include RELATIVE_BASE explicitly so we can mock now in tests
    local_timezone_str = user.timezone if user.timezone else 'US/Eastern'
    relative_base = util.now_local(local_timezone_str).replace(tzinfo=None)
    when = fixup_times(when, relative_base)
    parse_date_settings = {
            'PREFER_DATES_FROM': 'future',
            'PREFER_DAY_OF_MONTH': 'first',
            'TO_TIMEZONE': 'UTC',
            'TIMEZONE': local_timezone_str,
            'RETURN_AS_TIMEZONE_AWARE': True,
            'RELATIVE_BASE': relative_base}
    dt = dateparser.parse(when, settings=parse_date_settings)
    return dt

def regex(s):
    return re.compile(s, re.IGNORECASE)

def try_parse_reminder(message):

    def split_reminder_when(text):
        time_phrases = [regex("(.*)(" + p + ".*)") for p in (" every ", " today", " tomorrow",
            " next ", " sunday", " monday", " tuesday", " wednesday", " thursday", " friday",
            "saturday", " at ", " on ")]
        possible_whens = [] #(int, reminder, datetime) tuples

        for time_phrase in time_phrases:
            match = time_phrase.search(rest)
            if match:
                reminder_text = match.group(1).strip()
                when_text = match.group(2).strip()
                when = try_parse_when(when_text, user) # may be None
                possible_whens.append((len(when_text), reminder_text, when))

        great_whens = filter(lambda w: w[2], possible_whens)
        if len(great_whens):
            _, reminder_text, when = max(great_whens, key=lambda pair: pair[0])
        elif len(possible_whens):
            _, reminder_text, when = max(possible_whens, key=lambda pair: pair[0])
        else:
            reminder_text = rest
            when = None
        return reminder_text, when

    user = message.user()
    reminder2 = regex("remind me (.*?) to (.*)")
    match = reminder2.search(message.text)
    reminder_without_when = None
    if match:
        reminder_text = match.group(2)
        when = try_parse_when(match.group(1), user)
        if when:
            return Reminder(reminder_text, when, user.name, message.conv_id, message.db)
        else:
            reminder_without_when = reminder_text

    start_phrases = [regex(p + "(.*)") for p in ("remind me to ", "reminder to ")]
    for start_phrase in start_phrases:
        match = start_phrase.search(message.text)
        if match:
            rest = match.group(1)
            reminder_text, when = split_reminder_when(match.group(1))
            return Reminder(reminder_text, when, user.name, message.conv_id, message.db)

    if reminder_without_when:
        return Reminder(reminder_without_when, None, user.name, message.conv_id, message.db)
    return None

def try_parse_timezone(text):
    text = text.strip(" .?!,")
    start_tzs = [regex(p + "(.*)") for p in ("timezone", "time zone")]
    et = [regex(p + "$") for p in ("et", "eastern", "us/eastern")]
    pt = [regex(p + "$") for p in ("pt", "pacific", "us/pacific")]
    for start_tz in start_tzs:
        match = start_tz.search(text)
        if match:
            rest = match.group(1)
            words = rest.split(" ")
            for word in words:
                if any(map(lambda e: e.match(word), et)):
                    return "US/Eastern", True
                if any(map(lambda p: p.match(word), pt)):
                    return "US/Pacific", True
                try:
                    pytz.timezone(word)
                    return word, True
                except pytz.exceptions.UnknownTimeZoneError:
                    pass
            return None, True
    return None, False

def try_parse_stfu(text):
    text = text.lower().strip(" .!?,")
    return text == "nevermind" \
            or text == "never mind" \
            or text == "stop" \
            or text == "stfu" \
            or text == "shut up" \
            or text == "go away" \
            or text == "leave me alone" \
            or text == "never"

def try_parse_list(text):
    text = trimlower(text)
    return "list" in text \
            or ("show" in text and "reminders" in text) \
            or "upcoming" in text

def trimlower(s):
    return s.strip().lower()

def withoutchars(s, cs):
    for c in cs:
        s = s.replace(c, '')
    return s

def try_parse_source(text):
    s = trimlower(withoutchars(text, "\"'?"))
    forms = [
        "what are you made of",
        "what are you",
        "wheres the source",
        "how do you work",
        "what are you written in",
    ]
    if s in forms:
        return True
    return None

def heavy_cleanup(text, botname):
    text = text.replace("@" + botname, '')
    text = text.replace(botname, '')
    text = text.replace('  ', ' ')
    return trimlower(withoutchars(text, "\"'.,:!?"))

def try_parse_ack(text, config):
    text = heavy_cleanup(text, config.username)
    return text in ("ok", "thanks", "thank you", "cool", "great", "okay", "done", "will do",
            "thanx", "thanku", "thankyou", "thank u")

def try_parse_greeting(text, config):
    text = heavy_cleanup(text, config.username)
    greetings = ("hi", "hello", "hey", "hey there", "good morning", "good afternoon", "good evening")
    for g in greetings:
        if g in text:
            return g + "!"
    return None

def try_parse_undo(text, config):
    text = heavy_cleanup(text, config.username)
    undos = ("undo", "never ?mind", "no", "undo that", "delete that")
    for undo in undos:
        r = regex("(^|\s)" + undo + "($|\s)")
        if r.search(text):
            return True
    return None

def try_parse_delete_by_what(text):
    # TODO
    pass

def try_parse_delete_by_when(text):
    # TODO
    pass

def try_parse_delete_by_idx(text):
    # TODO
    pass

def parse_message(message, conv, config):
    reminder = try_parse_reminder(message)
    if reminder:
        return (MSG_REMINDER, reminder)

    if "help" in message.text.lower():
        return (MSG_HELP, None)

    if conv.context == conversation.CTX_WHEN:
        when = try_parse_when(message.text, message.user())
        if when is not None:
            return (MSG_WHEN, when)

    tz, attempted = try_parse_timezone(message.text)
    if tz is not None:
        return (MSG_TIMEZONE, tz)
    if attempted:
        return (MSG_UNKNOWN_TZ, None)

    if try_parse_list(message.text):
        return (MSG_LIST, None)

    if conv.is_strong_context():
        if try_parse_stfu(message.text):
            return (MSG_STFU, None)

    if conv.context in (conversation.CTX_SET, conversation.CTX_DELETED):
        if try_parse_undo(message.text, config):
            return (MSG_UNDO, None)

    source = try_parse_source(message.text)
    if source is not None:
        return (MSG_SOURCE, None)

    if conv.expects_ack() and try_parse_ack(message.text, config):
        return (MSG_ACK, None)

    greeting = try_parse_greeting(message.text, config)
    if not conv.is_recently_active() and greeting is not None:
        return (MSG_GREETING, greeting)

    return (MSG_UNKNOWN, None)


