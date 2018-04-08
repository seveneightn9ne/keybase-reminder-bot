# Utilities for interacting with the keybase chat api

import json, subprocess
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
    def __init__(self, json, db):
        self.text = json["msg"]["content"]["text"]["body"]
        self.author = json["msg"]["sender"]["username"]
        self.channel = json["msg"]["channel"]["name"]
        self.json = json
        self.db = db
        self.user_memoized = None

    def user(self):
        if not self.user_memoized:
            u = User.lookup(self.author, self.db)
            self.user_memoized = u
        return self.user_memoized

    def is_private_channel(self):
        return self.channel.count(',') == 1

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
    #print "finished keybase call"
    return json.loads(response)["result"]

def send(channel, text):
    call("send", {"options": {"channel": {"name": channel}, "message": {"body": text}}})
    return True
