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
        referrer.index("/login")
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
                return render_template("login.tmpl", referrer = referrer, error = error, title = "Login")
        finally:
            cnx.close()

        cookie = create_cookie(userid)
        response = flask.make_response(flask.redirect(referrer))
        response.set_cookie("session", cookie, expires=32503680000)
        return response

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if flask.request.method == "GET":
        return render_template('register.tmpl', title = 'Register', referrer = flask.request.referrer)

    username = flask.request.form["username"]
    password = flask.request.form["password"]
    email = flask.request.form["email"]
    referrer = flask.request.form["referrer"]

    cnx = get_mysql_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute('SELECT name FROM User WHERE name = %s', (username, ))
        cursor.next()
    except StopIteration:
        pass
    except:
        cnx.close()
        raise()
    else:
        return render_template("register.tmpl", error = "User already exists", referrer = referrer, title = 'Register')

    user_id = str(uuid.uuid4()).replace('-', '')
    
    try:
        cursor = cnx.cursor()
        cursor.execute("INSERT INTO User VALUES (UNHEX(%s), %s, %s, UNHEX(SHA2(%s, 256)))",
                       (user_id, username, email, password))
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
    cnx = get_mysql_connection()
    try:
        cursor = cnx.cursor()
        
    finally:
        cnx.close()

    return render_template("new.tmpl", title = "New Thread")

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

@bp.route('/action/edit/<edit_type>', methods=['POST'])
def edit(edit_type):
    renderer = flask.request.form["renderer"]
    content = flask.request.form["content"]
    referrer = flask.request.form["referrer"]
    post_id = flask.request.form["post_id"]
    thread_id = flask.request.form["thread_id"]

    user = read_cookie(flask.request.cookies["session"])

    cnx = get_mysql_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT HEX(author) FROM Post WHERE id = UNHEX(%s) AND author = UNHEX(%s)",
                       (post_id, user))
    except StopIteration:
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
            "INSERT INTO PostContent VALUES ("
            "UNHEX(%s), UNHEX(%s), UNHEX(%s), %s, %s, %s)",
            (post_content_id, post_id, user, content, renderer, now))

        cursor.execute(
            "UPDATE Post SET content = UNHEX(%s), last_modified = UNHEX(%s) WHERE id=UNHEX(%s)",
            (post_content_id, now, post_id))

        if edit_type == "thread":
            cursor.execute(
                "UPDATE Thread SET title = %s, category = UNHEX(%s), draft = %s "
                "WHERE id = UNHEX(%s)",
                (title, category, is_draft, thread_id))

        cnx.commit()
            
    finally:
        cnx.close()

    return flask.redirect(referrer)
