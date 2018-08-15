import flask
import datetime
import uuid
import traceback
import hashlib
import crypt

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

        cnx = get_pg_connection()
        try: 
            cursor = cnx.cursor()
            cursor.execute("SELECT salt FROM users WHERE name = %s", (username, ))
            salt = cursor.fetchone()
            if salt:
                salt = salt[0]
            else:
                error = "Wrong username or password"
                return render_template("login.tmpl", referrer=referrer, error=error, title="Login", type="login")
            hashed_password = hashlib.sha256((password + salt).encode()).hexdigest().upper()                    
            cursor.execute("SELECT user_id AS uid FROM users WHERE name = %s AND password = %s",
                           (username, hashed_password))
            
            ret = cursor.fetchone()
            if not ret:
                cnx.close()
                error = "Wrong username or password"
                return render_template("login.tmpl", referrer = referrer, error = error, title = "Login", type = "login")
        finally:
            cnx.close()

        userid = ret[0]
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
        cursor.execute("SELECT post.author, users.admin FROM post, users WHERE post.post_id = %s AND users.user_id = %s AND (post.author = users.user_id OR users.admin = TRUE)",
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

@bp.route('/search')
def search():
    query_string = flask.request.args.get('q');
    if not query_string:
        return render_template('search.tmpl', title="Search", query_string="")

    cnx = get_pg_connection();

    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT query.floor, query.post_id, query.thread_id, query.title, "
                       "pgroonga_snippet_html(query.content, pgroonga_query_extract_keywords(%s)) FROM "
                       "(SELECT post.post_id AS post_id, post.thread AS thread_id, post_content.content AS content, "
                       "rank() OVER (PARTITION BY post.thread ORDER BY post.datetime) AS floor, thread.title AS title "
                       "FROM post, post_content, thread WHERE post_content.post = post.post_id "
                       "AND post.thread = thread.thread_id "
                       "AND post.hidden = FALSE AND thread.hidden = FALSE "
                       "AND thread.draft = FALSE "
                       ") AS query WHERE query.content &@~ %s",
                       (query_string, query_string))
        ret = render_template("search.tmpl", title=query_string, cursor=cursor, query_string=query_string)
    finally:
        cnx.close()

    return ret

@bp.route('/userinfo', methods=['GET', 'POST'])
def userinfo():
    try:
        user = read_cookie(flask.request.cookies["session"])
    except KeyError:
        return flask.redirect("/")

    if not user:
        flask.redirect("/")

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute('SELECT name, email, nick, salt FROM users WHERE user_id = %s', (user, ))
        name, email, nick, salt = cursor.fetchone()
    finally:
        cnx.close()

    if flask.request.method == "GET":
        return render_template("userinfo.tmpl", error=False, name=name, email=email, nick=nick, title="User Info")
    else:
        try:
            email = flask.request.form["email"]
            nick = flask.request.form["nick"]
            old_password = flask.request.form["old_password"]
            new_password = flask.request.form["new_password"]
        except:
            return flask.abort(400)
            
        if new_password != "":
            cnx = get_pg_connection()
            cursor = cnx.cursor()
            try:
                hashed_old_password = hashlib.sha256((old_password + salt).encode()).hexdigest().upper()
                cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND password = %s",
                               (user, hashed_old_password))
                if not cursor.fetchone():
                    cnx.close()
                    return render_template("userinfo.tmpl", error=True, name=name, email=email, nick=nick, title="User Info")
            except:
                cnx.close()
                raise
                
            salt = crypt.mksalt(crypt.METHOD_SHA256)
            hashed_password = hashlib.sha256((new_password + salt).encode()).hexdigest().upper()
        else:
            hashed_password = None

        cnx = get_pg_connection()
        try:
            cursor = cnx.cursor()
            if hashed_password:
                print("password")
                cursor.execute("UPDATE users SET email = %s, nick = %s, password = %s, salt = %s WHERE user_id = %s",
                               (email, nick, hashed_password, salt, user))
            else:
                print("no password")
                cursor.execute("UPDATE users SET email = %s, nick = %s WHERE user_id = %s",
                               (email, nick, user))
            cnx.commit()
        finally:
            cnx.close()

        return flask.redirect("/userinfo")
