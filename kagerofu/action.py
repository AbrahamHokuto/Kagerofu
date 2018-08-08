import flask
import datetime
import uuid

from kagerofu.template import render_template
from kagerofu.database import get_mysql_connection
from kagerofu.cookie import read_cookie, create_cookie
from kagerofu import config

bp = flask.Blueprint("action", __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if flask.request.method == "GET":
        referrer = flask.request.referrer
    else:
        referrer = flask.request.form["referrer"]

    try:
        referrer.index("/login", title = "Login")
    except ValueError:
        pass
    else:
        referrer = "/"

    if flask.request.method == "GET":        
        return render_template("login.tmpl", title = "Login", referrer = flask.request.referrer, error = None)
    else:
        username = flask.request.form["username"]
        password = flask.request.form["password"]

        cnx = get_mysql_connection()
        try: 
            cursor = cnx.cursor()
            cursor.execute("SELECT HEX(id) AS uid FROM User WHERE name = %s AND password = UNHEX(SHA2(%s, 256))",
                           (username, password))
            try:
                userid = cursor.next()[0]
            except StopIteration:
                error = "Wrong username or password"
                return render_template("login.tmpl", referrer = referrer, error = error)
        finally:
            cnx.close()

        cookie = create_cookie(userid)
        response = flask.make_response(flask.redirect(referrer))
        response.set_cookie("session", cookie, expires=32503680000)
        return response

@bp.route('/logout')
def logout():
    referrer = flask.request.referrer

    print(referrer)
    try:
        referrer.index("/logout")
    except ValueError:
        pass
    else:
        referrer = "/"

    print(referrer)

    response = flask.make_response(flask.redirect(referrer))
    response.set_cookie("session", "", expires=0)
    return response

@bp.route('/new')
def new():
    cnx = get_mysql_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT HEX(id), name FROM Category")
        category_list = list(cursor)
        
    finally:
        cnx.close()

    return render_template("new.tmpl", title = "New Thread", categories = category_list)

@bp.route('/action/new_thread', methods=['POST'])
def new_thread():
    now = datetime.datetime.now()

    try:
        userid = read_cookie(flask.request.cookies["session"])
    except KeyError:
        flask.abort(401)

    if userid == None:
        flask.abort(401)

    title = flask.request.form["title"]
    category = flask.request.form["category"]
    renderer = flask.request.form["renderer"]
    content = flask.request.form["content"]
    is_draft = bool(int(flask.request.form["draft"]))

    thread_id = str(uuid.uuid4()).replace('-', '')
    post_id = str(uuid.uuid4()).replace('-', '')
    post_content_id = str(uuid.uuid4()).replace('-', '')

    cnx = get_mysql_connection()    
    try:
        cursor = cnx.cursor()
        cursor.execute("INSERT INTO Thread VALUES ("
                       "UNHEX(%s), UNHEX(%s), UNHEX(%s), %s, %s, FALSE, %s)",
                       (thread_id, userid, category, now, title, is_draft))
        
        cursor.execute("INSERT INTO Post VALUES ("
                       "UNHEX(%s), UNHEX(%s), UNHEX(%s), %s, FALSE, %s, UNHEX(%s))",
                       (post_id, userid, thread_id, now, now, post_content_id))

        cursor.execute("INSERT INTO PostContent VALUES ("
                       "UNHEX(%s), UNHEX(%s), UNHEX(%s), %s, %s, %s)",
                       (post_content_id, post_id, userid, content, renderer, now))
        cnx.commit()

    finally:
        cnx.close()

    return flask.redirect("/thread/view/" + thread_id)

@bp.route('/action/reply', methods=['POST'])
def reply():
    now = datetime.datetime.now()

    try:
        userid = read_cookie(flask.request.cookies["session"])
    except KeyError:
        flask.abort(401)

    if userid == None:
        flask.abort(401)

    renderer = flask.request.form["renderer"]
    content = flask.request.form["content"]
    thread_id = flask.request.form["thread_id"]

    post_id = str(uuid.uuid4()).replace('-', '')
    post_content_id = str(uuid.uuid4()).replace('-', '')

    cnx = get_mysql_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("INSERT INTO Post VALUES ("
                       "UNHEX(%s), UNHEX(%s), UNHEX(%s), %s, FALSE, %s, UNHEX(%s))",
                       (post_id, userid, thread_id, now, now, post_content_id))
        cursor.execute("INSERT INTO PostContent VALUES ("
                       "UNHEX(%s), UNHEX(%s), UNHEX(%s), %s, %s, %s)",
                       (post_content_id, post_id, userid, content, renderer, now))
        cnx.commit()
    finally:
        cnx.close()

    return flask.redirect(flask.request.referrer)
