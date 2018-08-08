import flask
import hashlib

from kagerofu.database import get_mysql_connection
from kagerofu.cookie import read_cookie

def render_template(template, **kwargs):
    args = {
        "title": "How do your end up here?",
        "body": "How do your end up here?"
    }

    try:
        cookie = read_cookie(flask.request.cookies["session"])
    except KeyError:
        cookie = None

    try:
        cnx = get_mysql_connection()
        cursor = cnx.cursor()
        cursor.execute('SELECT name, HEX(id) FROM Category ORDER BY id')
        categories = list(cursor)

        cursor = cnx.cursor()
        cursor.execute('SELECT name, email FROM User WHERE id = UNHEX(%s)', (cookie, ))
        try:
            user, avatar = cursor.next()
            avatar = hashlib.md5(avatar.strip().lower().encode("utf8")).hexdigest()
        except StopIteration:
            user, avatar = None, None

    finally:
        cnx.close()    

    kwargs["categories"] = categories
    kwargs["user"] = user
    kwargs["avatar"] = avatar
    kwargs["user_id"] = cookie

    return flask.render_template(template, **kwargs)
