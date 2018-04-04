#!/usr/bin/env python

import argparse, configparser, subprocess, sys, time

import keybase

def setup(username):
    try:
        subprocess.check_call(['keybase', 'login', username])
    except subprocess.CalledProcessError:
        print >> sys.stderr, "FATAL: Error during call to `keybase login " + username + "`"
        sys.exit(1)


def process_message(text):
    # TODO
    print "Received message:", text

def process_new_messages():
    results = keybase.call("list")
    all_convs = results["conversations"]
    unread_convs = filter(lambda conv: conv["unread"], all_convs)

    for conv in unread_convs:
        params = {"options": {
                "channel": {"name": conv["channel"]["name"]},
                "unread_only": True}}
        response = keybase.call("read", params)
        for message in response["messages"]:
            process_message(message["msg"]["content"]["text"]["body"])



def send_reminders():
    # TODO
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Beep boop.')
    parser.add_argument('--config', default='default.ini',
                        help='config file')
    args = parser.parse_args()

    config = configparser.ConfigParser()
    config.read(args.config)

    setup(config['keybase']['username'])

    while True:
        try:
            process_new_messages()
        except:
            pass

        try:
            send_reminders()
        except:
            pass

        time.sleep(1)

