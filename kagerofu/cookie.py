import hashlib

from kagerofu import config

def create_cookie(user):
    cookie_hash = hashlib.sha256((user + config["cookie_key"]).encode("utf8")).hexdigest()
    cookie = "{}|{}".format(user, cookie_hash)
    return cookie

def read_cookie(cookie):
    user, hashval = cookie.rsplit('|')
    if not hashlib.sha256((user + config["cookie_key"]).encode("utf8")).hexdigest() == hashval:
        return None

    return user
