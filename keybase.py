# Utilities for interacting with the keybase chat api

import json, subprocess, sys, time
from subprocess import PIPE
from user import User

class Message(object):
    '''
    Example message json: {
        u'msg': {
            u'unread': True,
            u'sent_at': 1522813326,
            u'sent_at_ms': 1522813326658,
            u'content': {u'text': {u'body': u'Hi'}, u'type': u'text'},
            u'prev': [{u'hash': u'DEZRY/2G+NYYgB34g1X9ocuFqfBBDIfEHvT+qOwotqE=', u'id': 1}],
            u'id': 2,
            u'channel': {
                u'members_type': u'impteamnative',
                u'topic_type': u'chat',
                u'name': u'jessk,reminderbot',
                u'public': False
            },
            u'bot_info': {
                u'bot_uid': 'f1f49e2da3db6392b47dc913b4e85519',
                u'bot_username': 'reminderbot'
            },
            u'sender': {
                u'username': u'jessk',
                u'device_name': u'phone',
                u'uid': u'653ba091fa61606e5a3c8fb2086b3419',
                u'device_id': u'c4aec52a455b551af3b042c46537fc18'
            }
        }
    }
        '''
    def __init__(self, conv_id, json, db):
        self.text = json["msg"]["content"]["text"]["body"]
        self.author = json["msg"]["sender"]["username"]
        self.conv_id = conv_id
        self.channel_json = json["msg"]["channel"]
        self.bot_username = json["msg"].get("bot_info", {}).get("bot_username")
        self.json = json
        self.db = db

    @classmethod
    def inject(cls, text, author, conv_id, channel, db):
        return Message(conv_id, {"msg": {
            "content": {"text": {"body": text}},
            "sender": {"username": author},
            "channel": {
                "name": channel,
                "members_type": "impteamnative"}}}, db)

    def user(self):
        return User.lookup(self.author, self.db)

    def is_private_channel(self):
        # `jessk,reminderbot` or `jessk` with reminderbot as a bot or
        # restricted bot member
        return self.channel_json["members_type"] != "team" and self.channel_json["name"].count(',') <= 1

def call(method, params=None, retries=0):
    # method: string, params: dict
    # return: dict
    #print "keybase call " + method
    #print "will call keybase " + method
    if params is None:
        params = {}
    query = {"method": method, "params": params}
    proc = subprocess.Popen(['keybase','chat','api'], stdin=PIPE, stdout=PIPE)
    proc.stdin.write((json.dumps(query) + "\n").encode('utf-8'))
    proc.stdin.close()
    response = proc.stdout.readline()
    try:
        j = json.loads(response.decode('utf-8'))
    except Exception as e:
        if retries < 3:
            print("Unable to parse json from:", response)
            time.sleep(1)
            return call(method, params, retries+1)
        else:
            raise e

    if "error" in j:
        print("Problem with query:", query)
        raise Exception(j["error"]["message"])

    return j["result"]

def send(conv_id, text):
    call("send", {"options": {"conversation_id": conv_id, "message": {"body": text}}})
    return True, None

def debug_crash(message, config):
    debug(message, config)
    if config.autosend_logs:
        try:
            subprocess.check_call(['keybase', 'log', 'send',
                '--feedback', 'reminderbot crash', '--no-confirm'])
        except subprocess.CalledProcessError:
            print("Error during call to `keybase log send`", file=sys.stderr)

def debug(message, config):
    if config.debug_team and config.debug_topic:
        call("send", {"options": {"channel": {
            "name": config.debug_team,
            "members_type": "team",
            "topic_name": config.debug_topic},
            "message": {"body": message}}})
    else:
        print("[DEBUG]", message, file=sys.stderr)

def _status():
    proc = subprocess.Popen(['keybase','status', '-j'], stdout=PIPE)
    out, err = proc.communicate()
    return json.loads(out.decode('utf-8'))

def setup(config):
    status = _status()
    logged_in = status["Username"]
    if not status["LoggedIn"]:
        try:
            subprocess.check_call(['keybase', 'login', config.username])
        except subprocess.CalledProcessError:
            print("FATAL: Error during call to `keybase login " \
                    + config.username + "`", file=sys.stderr)
            sys.exit(1)
    elif not logged_in == config.username:
        print("FATAL: Logged in to Keybase as wrong user.", file=sys.stderr)
        print("Logged in as "+logged_in+" but expected "+config.username+". ", file=sys.stderr)
        print("Run `keybase logout` to log them out.", file=sys.stderr)
        sys.exit(1)


    # Disable typing notifications
    try:
        subprocess.check_call(['keybase', 'chat', 'notification-settings', '--disable-typing'])
    except subprocess.CalledProcessError as e:
        print("Error during disabling typing notifications", e.message, file=sys.stderr)

    if config.debug_team and config.debug_topic:
        try:
            call("read", {"options": {"channel": {
                "name": config.debug_team,
                "members_type": "team",
                "topic_name": config.debug_topic}}})
        except Exception as e:
            print("Can't read from the debug channel:", file=sys.stderr)
            print(e.message, file=sys.stderr)
            sys.exit(1)


def advertise_commands():
    remind_me_extended = """Set a reminder at a specific time. Examples:
    ```
    !remind me [when] to [what]
    !remind me to [what] [when]```"""
    delete_extended = """Examples:
    ```
    !delete the reminder to [what]
    !delete the [when] reminder
    !delete reminder #2```"""
    tz_extended = """Set your timezone to [tz]. This changes when any upcoming reminders will happen. Examples:
    ```
    !timezone GMT
    !timezone US/Pacific```"""
    call("advertisecommands", {"options": {
        "alias": "Reminder Bot",
        "advertisements": [{
            "type": "public",
            "commands": [
                    {
                    "name": "help",
                    "description": "See help with available commands.",
                    },
                    {
                    "name": "remind me",
                    "description": "Set a reminder.",
                    "extended_description": {
                            "title": "*!remind me*",
                            "desktop_body": remind_me_extended,
                            "mobile_body": remind_me_extended,
                        }
                    },
                    {
                    "name": "list",
                    "description": "Show upcoming reminders.",
                    },
                    {
                    "name": "delete",
                    "description": "Delete a reminder.",
                    "extended_description": {
                            "title": "*!delete*",
                            "desktop_body": delete_extended,
                            "mobile_body": delete_extended,
                        }
                    },
                    {
                    "name": "timezone",
                    "description": "Set your timezone.",
                    "extended_description": {
                            "title": "*!timezone*",
                            "desktop_body": tz_extended,
                            "mobile_body": tz_extended,
                        }
                    },
                    {
                    "name": "source",
                    "description": "Learn about my beginnings.",
                    },
                ],
            }],
        }
    })

def clear_command_advertisements():
    call("clearcommands")
