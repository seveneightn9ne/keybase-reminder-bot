# Parsing messages

import dateparser, pytz, re

import conversation, util
from reminders import Reminder
from user import User

MSG_UNKNOWN = 0
MSG_REMINDER = 1
MSG_HELP = 2
MSG_WHEN = 3
MSG_TIMEZONE = 4
MSG_STFU = 5
MSG_UNKNOWN_TZ = 6
MSG_LIST = 7
MSG_SOURCE = 8
# TODO MSG_SNOOZE
# TODO MSG_ACK
# TODO MSG_GREETING
# TODO MSG_LIST
# TODO MSG_CANCEL

def try_parse_when(when, user):
    # include RELATIVE_BASE explicitly so we can mock now in tests
    local_timezone_str = user.timezone if user.timezone else 'US/Eastern'
    relative_base = util.now_local(local_timezone_str).replace(tzinfo=None)
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
    reminder2 = regex("remind me (.*) to (.*)")
    match = reminder2.search(message.text)
    if match:
        reminder_text = match.group(2)
        when = try_parse_when(match.group(1), user)
        if when:
            return Reminder(reminder_text, when, user.name, message.conv_id, message.db)
        # else: Ideally we'd try the following block and if that doesn't find a when
        # then assume we're in this case but couldn't read the when. But whatever.

    start_phrases = [regex(p + "(.*)") for p in ("remind me to ", "reminder to ")]
    for start_phrase in start_phrases:
        match = start_phrase.search(message.text)
        if match:
            rest = match.group(1)
            reminder_text, when = split_reminder_when(match.group(1))
            return Reminder(reminder_text, when, user.name, message.conv_id, message.db)

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
    table = dict.fromkeys(map(ord, cs), None)
    return s.translate(table)

def try_parse_source(text):
    s = withoutchars(trimlower(text), "\"'")
    if s[-1] != "?":
        return None
    s = withoutchars(s[:-1], "?")
    forms = [
        "what are you made of",
        "what are you",
        "wheres the source",
        "how do you work",
        "what are you written in",
    ]
    for form in forms:
        if s == form:
            return True
    return False

def parse_message(message, conv):
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

    if try_parse_stfu(message.text):
        return (MSG_STFU, None)

    source = try_parse_source(message.text)
    if source is not None:
        return (MSG_SOURCE, source)

    return (MSG_UNKNOWN, None)


