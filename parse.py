# Parsing messages

import dateparser, itertools, nltk, pytz, re

import conversation, util
from reminders import Reminder, Repetition, INTERVALS
from user import User
from collections import namedtuple
from datetime import datetime, timedelta # don't use anything that uses now.
from keybase import debug

MSG_UNKNOWN    = "UNKNOWN"
MSG_REMINDER   = "REMINDER"
MSG_HELP       = "HELP"
MSG_WHEN       = "WHEN"
MSG_TIMEZONE   = "TIMEZONE"
MSG_STFU       = "STFU"
MSG_UNKNOWN_TZ = "UNKNOWN_TZ"
MSG_LIST       = "LIST"
MSG_SOURCE     = "SOURCE"
MSG_ACK        = "ACK"
MSG_GREETING   = "GREETING"
MSG_UNDO       = "UNDO"
MSG_DEBUG      = "DEBUG"
MSG_NODEBUG    = "NODEBUG"
MSG_SNOOZE     = "SNOOZE"
MSG_DELETE     = "DELETE"

def try_parse_when(when, user):
    def fixup_times(when_str, relative_base):
        # When there is no explicit AM/PM assume the next upcoming one
        # H:MM (AM|PM)?

        def hhmm_explicit_ampm(when_str, relative_base):
            # looks for HH:MM without an AM or PM and adds 12 to the HH if necessary.
            # Returns str if the returned str is good to go, None if it's not fixed.
            time_with_minutes = regex('(?:[^\w]|^)(\d\d?(:\d\d))(\s?[ap]\.?m)?')
            results = re.findall(time_with_minutes, when_str)
            if len(results) != 1:
                # I don't expect to find more than one time. Rather not do anything.
                return None
            time_match, mins_match, ampm_match = results[0]
            if ampm_match:
                # AM/PM is explicit
                return when_str

            time = datetime.strptime(time_match, '%I:%M')

            if time.hour > 12:
                return when_str # you explicitly are after noon e.g. 23:00

            if relative_base.hour > time.hour:
                new_hour = str(time.hour + 12)
                return when_str.replace(time_match, new_hour + mins_match)

            return None

        def at_hh_explicit_ampm(when_str, relative_base):
            # looks for "at HH" without AM/PM and adds 12 to HH and :00 if necessary.
            at_hh_regex = regex('(?:(?:^|\s)at\s|^)(\d\d?)($|\s?[ap]\.?m\.?(?:$|[^\w]))')
            results = re.findall(at_hh_regex, when_str)
            if len(results) != 1:
                # I don't expect to find more than one time. Rather not do anything.
                return None
            hour_match, ampm_match = results[0]
            when_with_minutes = when_str.replace(hour_match, hour_match + ":00")
            if ampm_match:
                # AM/PM is explicit
                return when_with_minutes

            time = datetime.strptime(hour_match, '%I')

            if time.hour > 12:
                return when_with_minutes # you explicitly are after noon e.g. 23:00

            if relative_base.hour > time.hour:
                new_hour = str(time.hour + 12)
                return when_with_minutes.replace(hour_match, new_hour)

            return when_with_minutes

        new_when = hhmm_explicit_ampm(when_str, relative_base)
        if new_when:
            return new_when
        new_when = at_hh_explicit_ampm(when_str, relative_base)
        if new_when:
            return new_when
        # else... none of the fixes worked
        return when_str

    def extract_repetition(when_str):
        # Returns a new when_str, Repetition
        if not "every" in when_str:
            return when_str, Repetition(None, None)
        days = set(["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"])
        intervals_day = set(["day", "night", "evening", "morning", "afternoon"])
        intervals = set(INTERVALS)
        # 0: nth; 1: interval; 2: rest (e.g. "at 2pm")
        regexes = [regex("(?:on )?every (?:(?P<nth>\w+) )?(?P<interval>" + i + ")s?(?:$|(?: (?P<rest>.+)))") for i in days | intervals_day | intervals]

        for r in regexes:
            match = r.search(when_str)
            if match:
                nth_text = match.group('nth')
                interval = match.group('interval')
                rest = match.group('rest')
                if nth_text:
                    nths = {"other": 2, "second": 2, "third": 3, "fourth": 4}
                    if nth_text in nths:
                        nth = nths[nth_text]
                    else:
                        nth_regex = regex("(\d+)[a-z]*")
                        nth_match = nth_regex.search(nth_text)
                        if nth_match:
                            nth = int(match.group(1))
                        else:
                            # an nth that I don't understand.
                            # TODO this is what posting to debug channel is for
                            nth = 1
                else:
                    nth = 1
                if interval in intervals_day:
                    interval = "day"
                if interval in days:
                    if rest:
                        rest = interval + " " + rest
                    else:
                        rest = "on " + interval
                    interval = "week"
                if not rest:
                    rest = "in " + str(nth) + " " + interval + ("s" if nth > 1 else "")
                return rest, Repetition(interval, nth)
        return when_str, Repetition(None, None)
    
    # include RELATIVE_BASE explicitly so we can mock now in tests
    local_timezone_str = user.timezone if user.timezone else 'US/Eastern'
    relative_base = util.now_local(local_timezone_str).replace(tzinfo=None)
    when = fixup_times(when, relative_base)
    when, repetition = extract_repetition(when)
    parse_date_settings = {
            'PREFER_DATES_FROM': 'future',
            'PREFER_DAY_OF_MONTH': 'first',
            'TO_TIMEZONE': 'UTC',
            'TIMEZONE': local_timezone_str,
            'RETURN_AS_TIMEZONE_AWARE': True,
            'RELATIVE_BASE': relative_base}
    dt = dateparser.parse(when, settings=parse_date_settings)
    if dt != None and (dt - util.now_utc()).total_seconds() < 0:
        return None, None
    return dt, repetition

def regex(s):
    return re.compile(s, re.IGNORECASE)

def try_parse_reminder(message):

    def split_reminder_when(text):
        time_phrases = [regex("(.*)(" + p + ".*)") for p in (" every ", " today", " tomorrow",
            " next ", " sunday", " monday", " tuesday", " wednesday", " thursday", " friday",
            "saturday", " at ", " on ", " in ")]
        possible_whens = [] #(int, reminder, datetime) tuples

        for time_phrase in time_phrases:
            match = time_phrase.search(text)
            if match:
                reminder_text = match.group(1).strip()
                when_text = match.group(2).strip()
                when, repetition = try_parse_when(when_text, user) # may be None
                possible_whens.append((len(when_text), reminder_text, when, repetition))

        great_whens = filter(lambda w: w[2], possible_whens)
        if len(great_whens):
            _, reminder_text, when, repetition = max(great_whens, key=lambda pair: pair[0])
        elif len(possible_whens):
            _, reminder_text, when, repetition = max(possible_whens, key=lambda pair: pair[0])
        else:
            reminder_text = text
            repetition = None
            when = None
        return reminder_text, when, repetition

    # Order: "remind" <when> "to" <what>
    user = message.user()
    reminder_without_when = None
    reminder2 = regex("(?:remind me|reminder) (.*?) to (.*)")
    match = reminder2.search(message.text)
    if match:
        reminder_text = match.group(2)
        when, repetition = try_parse_when(match.group(1), user)
        if when:
            return Reminder(reminder_text, when, repetition, user.name, message.conv_id, message.db)
        else:
            reminder_without_when = reminder_text

    # Order: "remind" <what> "to" <when>
    match = regex("(?:remind me|reminder) to (.*)").search(message.text)
    if match:
        reminder_text, when, repetition = split_reminder_when(match.group(1))
        return Reminder(reminder_text, when, repetition, user.name, message.conv_id, message.db)

    if reminder_without_when:
        return Reminder(reminder_without_when, None, None, user.name, message.conv_id, message.db)
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
    acks = ("ok", "k", "thanks", "thx", "thank you", "cool", "great", "okay", "done", "will do",
            "thanx", "thanku", "thankyou", "thank u")
    if text in acks:
        return True
    words = re.split(r"\W+", text)
    if all(word in acks for word in words):
        return True
    return None

def try_parse_greeting(text, config):
    text = heavy_cleanup(text, config.username)
    greetings = ("hi", "hello", "hey", "hey there", "good morning", "good afternoon", "good evening")
    for g in greetings:
        if g in text:
            return g + "!"
    return None

def try_parse_undo(text, config):
    text = heavy_cleanup(text, config.username)
    undos = ("undo", "never ?mind", "no", "undo that", "delete that", "nvm")
    for undo in undos:
        r = regex("(^|\s)" + undo + "($|\s)")
        if r.search(text):
            return True
    return None

delete_words = ("delete", "cancel", "undo", "remove", "clear")
delete_patterns = [regex(d + " (.*) reminder") for d in delete_words] \
    + [regex(d + ".* reminder " + a + " (.*)") for d in delete_words \
        for a in ("in", "at", "on", "to", "for", "about")]
delete_idx_patterns = [regex(d + " .*[^\w](\d+)") for d in delete_words]

def try_parse_delete_by_when_or_what(text, reminders, user):
    # delete the 10am reminder
    # delete the meeting reminder
    # delete the reminder for 10am
    # delete the reminder for a meeting
    # delete the reminder on tuesday
    # delete the reminder to go to work
    # TODO: delete my next reminder
    # TODO: delete the reminder for tomorrow/tonight/etc
    text_matches = []
    when_matches = []
    for r in delete_patterns:
        match = r.search(text)
        if match:
            match_text = match.group(1)
            text_matches.append(match_text)
            when, _ = try_parse_when(match_text, user)
            if when:
                when_matches.append(when)
    
    if len(text_matches) == len(when_matches) == 0:
        return None

    reminder_matches = []
    reminder_x_when = itertools.product(reminders, when_matches)
    reminder_x_text = itertools.product(reminders, text_matches)

    for (reminder, when) in reminder_x_when:
        if abs(reminder.reminder_time - when) < timedelta(minutes=1):
            reminder_matches.append((reminder, 10))
        elif reminder.reminder_time == when + timedelta(days=1):
            reminder_matches.append((reminder, 5))

    for (reminder, text) in reminder_x_text:
        tagged_words = nltk.pos_tag(nltk.word_tokenize(text), tagset='universal')
        words = [word for (word, tag) in tagged_words if tag in ["ADJ", "NOUN", "NUM", "VERB", "X"]]
        matches = len([w for w in nltk.word_tokenize(reminder.body) if w in words])
        if matches:
            reminder_matches.append((reminder, matches**2))

    if len(reminder_matches) == 0:
        return None

    return max(reminder_matches, key=lambda (w,s): s)[0]

def try_parse_delete_by_idx(text, reminders):
    for r in delete_idx_patterns:
        match = r.search(text)
        if match:
            i = int(match.group(1))
            if 0 < i <= len(reminders):
                return reminders[i-1]

def try_parse_delete(message, reminders):

    if len(reminders) == 0:
        return None

    # Try when before idx because idx would incorrectly match on when
    r = try_parse_delete_by_when_or_what(message.text, reminders, message.user())
    if r:
        return r

    r = try_parse_delete_by_idx(message.text, reminders)
    if r:
        return r


def try_parse_debug(text):
    return text == "#debug"

def try_parse_nodebug(text):
    return text == "#nodebug"

SnoozeData = namedtuple("SnoozeData", ["phrase", "time"])

def try_parse_snooze(text, user, config):
    text = heavy_cleanup(text, config.username)
    match = regex(r"^snooze\s+(?:for)?\s*(.*)$").match(text)
    if not match and text != "snooze":
        return None
    if match:
        phrase = match.group(1)
    else:
        phrase = "10 minutes"
    t, _ = try_parse_when("in " + phrase, user)
    if t:
        return SnoozeData(phrase, t)

def parse_message(message, conv, config):

    reminder = try_parse_delete(message, conv.get_all_reminders())
    if reminder:
        return (MSG_DELETE, reminder)

    reminder = try_parse_reminder(message)
    if reminder:
        return (MSG_REMINDER, reminder)

    if "help" in message.text.lower():
        return (MSG_HELP, None)

    if conv.context == conversation.CTX_WHEN:
        when, repetition = try_parse_when(message.text, message.user())
        if when is not None:
            return (MSG_WHEN, (when, repetition))

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
    if greeting is not None:
        return (MSG_GREETING, greeting)

    if try_parse_debug(message.text):
        return (MSG_DEBUG, None)

    if try_parse_nodebug(message.text):
        return (MSG_NODEBUG, None)

    if conv.context == conversation.CTX_REMINDED:
        data = try_parse_snooze(message.text, message.user(), config)
        if data:
            return (MSG_SNOOZE, data)

    return (MSG_UNKNOWN, None)
