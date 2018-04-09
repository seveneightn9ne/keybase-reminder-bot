# Parsing messages

import dateparser, datetime, pytz

import conversation
from reminders import Reminder
from user import User

MSG_UNKNOWN = 0
MSG_REMINDER = 1
MSG_HELP = 2
MSG_WHEN = 3
MSG_TIMEZONE = 4
MSG_STFU = 5
MSG_UNKNOWN_TZ = 6
# TODO MSG_SNOOZE
# TODO MSG_ACK
# TODO MSG_GREETING
# TODO MSG_LIST
# TODO MSG_CANCEL

def try_parse_when(when, user):
    # include RELATIVE_BASE explicitly so we can mock datetime.now in tests
    local_timezone_str = user.timezone if user.timezone else 'US/Eastern'
    relative_base = datetime.datetime.now(tz=pytz.utc).astimezone(
            pytz.timezone(local_timezone_str))
    parse_date_settings = {
            'PREFER_DATES_FROM': 'future',
            'PREFER_DAY_OF_MONTH': 'first',
            'TO_TIMEZONE': 'UTC',
            'TIMEZONE': local_timezone_str,
            'RETURN_AS_TIMEZONE_AWARE': True,
            'RELATIVE_BASE': relative_base}
    return dateparser.parse(when, settings=parse_date_settings)

def try_parse_reminder(message):
    start_phrases = ["remind me to ", "reminder to "]
    time_phrases = [" every ", " today", " tomorrow", " next ", " sunday", " monday",
            " tuesday", " wednesday", " thursday", " friday", "saturday", " at ", " on "]
    for start_phrase in start_phrases:
        if start_phrase in message.text.lower():
            rest = message.text.split(start_phrase)[-1]
            break
    else:
        return None

    for time_phrase in time_phrases:
        if time_phrase in rest.lower():
            parts = rest.split(time_phrase)
            if len(parts) == 2:
                reminder_text = parts[0]
                when = (time_phrase + parts[1]).strip()
            else:
                reminder_text = parts[:-1].join(time_phrase)
                when = (time_phrase + parts[-1]).strip()
            break
    else:
        reminder_text = rest
        when = ""

    user = message.user()

    # need to fill in reminder time
    reminder = Reminder(reminder_text, None, user.name, message.channel, message.db)

    if not when or when.lower().startswith("every"):
        # TODO every
        return reminder # will ask for when

    reminder.reminder_time = try_parse_when(when, user)
    #print "Reminder time parsed as", reminder.reminder_time

    return reminder

def try_parse_timezone(text):
    text = text.lower().strip(" .?!,")
    start_tzs = ["timezone", "time zone"]
    for start_tz in start_tzs:
        if start_tz in text:
            rest = text.split(start_tz)[-1]
            words = rest.split(" ")
            for word in words:
                if word == "et" or word == "eastern" or word == "us/eastern":
                    return "US/Eastern", True
                if word == "pt" or word == "pacific" or word == "us/pacific":
                    return "US/Pacific", True
                try:
                    dateparser.parse("today", settings={"TIMEZONE": word})
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

    if try_parse_stfu(message.text):
        return (MSG_STFU, None)

    return (MSG_UNKNOWN, None)


