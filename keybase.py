# Utilities for interacting with the keybase chat api

import json, subprocess
from subprocess import PIPE

def call(method, params=None):
    # method: string, params: dict
    # return: dict
    if params is None:
        params = {}
    query = {"method": method, "params": params}
    proc = subprocess.Popen(['keybase','chat','api'], stdin=PIPE, stdout=PIPE)
    proc.stdin.write(json.dumps(query) + "\n")
    proc.stdin.close()
    response = proc.stdout.readline()
    return json.loads(response)["result"]


