# Utilities for interacting with the keybase chat api

import asyncio, json, sys
from user import User
from pykeybasebot.types import chat1

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
        print(json)
        self.text = json["msg"]["content"]["text"]["body"]
        self.author = json["msg"]["sender"]["username"]
        self.conv_id = conv_id
        self.channel_members_type =json["msg"]["channel"]["members_type"]
        self.channel_name = json["msg"]["channel"]["name"]
        self.bot_username = (json["msg"].get("bot_info", {}) or {}).get("bot_username")
        self.db = db

    @classmethod
    def from_msgsummary(cls, msg_summary, db):
        return Message(
            msg_summary.conv_id,
            {"msg": json.loads(msg_summary.to_json())},
            db
        )
        # self.text = msg_summary.content.text.body
        # self.author = msg_summary.sender.username
        # self.conv_id = msg_summary.conv_id
        # self.channel_members_type = msg_summary.channel.members_type
        # self.channel_name = msg_summary.channel.name
        # self.bot_username = msg_summary.bot_info.bot_username if msg_summary.bot_info else None
        # self.db = db

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
        return self.channel_members_type != "team" and self.channel_name.count(',') <= 1

async def send(bot, conv_id, msg):
    async def _send():
        await bot.chat.send(conv_id, msg)
    await _with_retries(_send)

async def debug(bot, conv, message, config):
    channel = _debug_channel(config)
    if conv.debug and channel:
        await send(bot, channel, message)
    else:
        print("[DEBUG]", message, file=sys.stderr)

async def _with_retries(fn, retries=3):
    try:
        await fn()
    except Exception as e:
        if retries:
            await asyncio.sleep(1)
            await _with_retries(fn, retries-1)
        else:
            raise e

def _debug_channel(config):
    if not config.debug_team or not config.debug_topic:
        return None
    return chat1.ChatChannel(name=config.debug_team, members_type="team",topic_name=config.debug_topic)
