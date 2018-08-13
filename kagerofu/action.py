import flask
import datetime
import uuid
import traceback
import hashlib

from kagerofu.template import render_template
from kagerofu.database import get_pg_connection
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
        referrer.index("/login")
    except ValueError:
        pass
    else:
        referrer = "/"

    if flask.request.method == "GET":        
        return render_template("login.tmpl", title = "Login", referrer = flask.request.referrer, error = None, type = "login")
    else:
        username = flask.request.form["username"]
        password = flask.request.form["password"]

        hashed_password = hashlib.sha256(password.encode()).hexdigest().upper()

        cnx = get_pg_connection()
        try: 
            cursor = cnx.cursor()
            cursor.execute("SELECT user_id AS uid FROM users WHERE name = %s AND password = %s",
                           (username, hashed_password))
            
            userid = cursor.fetchone()[0]
            if not userid:
                cnx.close()
                error = "Wrong username or password"
                return render_template("login.tmpl", referrer = referrer, error = error, title = "Login", type = "login")
        finally:
            cnx.close()
            
        cookie = create_cookie(userid)
        response = flask.make_response(flask.redirect(referrer))
        response.set_cookie("session", cookie, expires=32503680000)
        return response

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if flask.request.method == "GET":
        return render_template('login.tmpl', title = 'Register', referrer = flask.request.referrer, type = "register")

    username = flask.request.form["username"]
    password = flask.request.form["password"]
    email = flask.request.form["email"]
    referrer = flask.request.form["referrer"]

    cnx = get_pg_connection()

    cursor = cnx.cursor()
    cursor.execute('SELECT name FROM users WHERE name = %s', (username, ))
    if cursor.fetchone():
        cnx.close()
        return render_template("login.tmpl", error = "User already exists", referrer = referrer, title = 'Register', type = "register")

    user_id = str(uuid.uuid4()).replace('-', '')

    hashed_password = hashlib.sha256(password.encode()).hexdigest().upper()
    
    try:
        cursor = cnx.cursor()
        cursor.execute("INSERT INTO users VALUES (%s, %s, %s, %s, %s, FALSE, FALSE, '')",
                       (user_id, username, email, hashed_password, username))
        cnx.commit()
    finally:
        cnx.close()

    cookie = create_cookie(user_id)
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
    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        
    finally:
        cnx.close()

    return render_template("edit.tmpl", title = "New Thread", type="new_thread")

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

    cnx = get_pg_connection()    
    try:
        cursor = cnx.cursor()
        cursor.execute("INSERT INTO thread VALUES ("
                       "%s, %s, %s, %s, %s, FALSE, %s )",
                       (thread_id, userid, category, now, title, bool(is_draft)))
        
        cursor.execute("INSERT INTO post VALUES ("
                       "%s, %s, %s, %s, FALSE, %s, %s)",
                       (post_id, userid, thread_id, now, now, post_content_id))

        cursor.execute("INSERT INTO post_content VALUES ("
                       "%s, %s, %s, %s, %s)",
                       (post_content_id, post_id, renderer, content, now))
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

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("INSERT INTO post VALUES ("
                       "%s, %s, %s, %s, FALSE, %s, %s)",
                       (post_id, userid, thread_id, now, now, post_content_id))
        cursor.execute("INSERT INTO post_content VALUES ("
                       "%s, %s, %s, %s, %s)",
                       (post_content_id, post_id, renderer, content, now))
        cnx.commit()
    finally:
        cnx.close()

    return flask.redirect(flask.request.referrer)

@bp.route('/action/edit/<edit_type>', methods=['POST'])
def edit(edit_type):
    renderer = flask.request.form["renderer"]
    content = flask.request.form["content"]
    referrer = flask.request.form["referrer"]
    post_id = flask.request.form["post_id"]

    user = read_cookie(flask.request.cookies["session"])

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT author FROM post WHERE post_id = %s AND author = %s",
                       (post_id, user))
        if not cursor.fetchone():            
            cnx.close()
            flask.abort(401)
    except:
        cnx.close()
        raise

    if edit_type == "thread":
        thread_id = flask.request.form["thread_id"]
        title = flask.request.form["title"]
        category = flask.request.form["category"]
        is_draft = bool(int(flask.request.form["draft"]))

    post_content_id = str(uuid.uuid4()).replace('-', '')
    now = datetime.datetime.now()

    try:
        cursor = cnx.cursor()
        cursor.execute(
            "INSERT INTO post_content VALUES ("
            "%s, %s, %s, %s, %s)",
            (post_content_id, post_id, renderer, content, now))

        cursor.execute(
            "UPDATE post SET content = %s, last_modified = %s WHERE post_id=%s",
            (post_content_id, now, post_id))

        if edit_type == "thread":
            cursor.execute(
                "UPDATE thread SET title = %s, category = %s, draft = %s "
                "WHERE thread_id = %s",
                (title, category, is_draft, thread_id))
        cnx.commit()
    except:
        traceback.print_exc()
        
    finally:
        cnx.close()

    return flask.redirect(referrer)
