import flask
import hashlib

from kagerofu.database import get_pg_connection
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
        cnx = get_pg_connection()
        cursor = cnx.cursor()
        cursor.execute('SELECT name, category_id FROM category ORDER BY category_id')
        categories = list(cursor)

        cursor = cnx.cursor()
        cursor.execute('SELECT nick, email, admin FROM users WHERE user_id = %s', (cookie, ))

        result = cursor.fetchone()

        if result:
            user, avatar, admin = result
            avatar = hashlib.md5(avatar.strip().lower().encode("utf8")).hexdigest()
        else:
            user, avatar, admin = None, None, None

    finally:
        cnx.close()

    kwargs["categories"] = categories
    kwargs["user"] = user
    kwargs["avatar"] = avatar
    kwargs["user_id"] = cookie
    kwargs["admin"] = admin

    return flask.render_template(template, **kwargs)
