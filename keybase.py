# Utilities for interacting with the keybase chat api

import json, subprocess, sys
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
                u'public': False},
            u'sender': {
                u'username': u'jessk',
                u'device_name': u'phone',
                u'uid': u'653ba091fa61606e5a3c8fb2086b3419',
                u'device_id': u'c4aec52a455b551af3b042c46537fc18'}}}]}
        '''
    def __init__(self, conv_id, json, db):
        self.text = json["msg"]["content"]["text"]["body"]
        self.author = json["msg"]["sender"]["username"]
        self.conv_id = conv_id
        self.channel_json = json["msg"]["channel"]
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
        return self.channel_json["name"].count(',') == 1

def call(method, params=None):
    # method: string, params: dict
    # return: dict
    #print "keybase call " + method
    #print "will call keybase " + method
    if params is None:
        params = {}
    query = {"method": method, "params": params}
    proc = subprocess.Popen(['keybase','chat','api'], stdin=PIPE, stdout=PIPE)
    proc.stdin.write(json.dumps(query) + "\n")
    proc.stdin.close()
    response = proc.stdout.readline()
    j = json.loads(response)
    if "error" in j:
        print "Problem with query:", query
        raise Exception(j["error"]["message"])

    return j["result"]

def send(conv_id, text):
    call("send", {"options": {"conversation_id": conv_id, "message": {"body": text}}})
    return True

def _status():
    proc = subprocess.Popen(['keybase','status', '-j'], stdout=PIPE)
    out, err = proc.communicate()
    return json.loads(out)

def setup(username):
    status = _status()
    if not status["LoggedIn"]:
        try:
            subprocess.check_call(['keybase', 'login', username])
        except subprocess.CalledProcessError:
            print >> sys.stderr, "FATAL: Error during call to `keybase login " \
                    + username + "`"
            sys.exit(1)
    elif not status["Username"] == username:
        print >> sys.stderr, "FATAL: There's another user logged in to Keybase already." \
                " You'll need to log them out first."
        sys.exit(1)
