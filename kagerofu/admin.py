import flask
import hashlib
import uuid

bp = flask.Blueprint("admin", __name__)

from kagerofu.cookie import read_cookie, create_cookie
from kagerofu.database import get_pg_connection, get_redis_connection
from kagerofu.template import render_template
from kagerofu.logging import write_log, log_data_simple, log_type_to_string

def check_permission():
    session = flask.request.cookies.get("session")
    if session == None or read_cookie(session) == None:
        write_log("dashboard_access", "", {"success": False})
        flask.abort(401)

    user = read_cookie(session)

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = %s AND admin = TRUE", (user, ))
        result = (cursor.fetchone() != None)
    finally:
        cnx.close()

    if not result:
        write_log("dashboard_access", user, {"success": False})
        flask.abort(401)

    return user

def check_sudo(user):
    sudo_mode = flask.request.cookies.get("sudo_mode")
    if sudo_mode == None or read_cookie(sudo_mode) == None:
        return False

    if user != read_cookie(sudo_mode):
        return False

    return True

@bp.route("/sudo", methods = ['GET', 'POST'])
def sudo():
    user = check_permission()

    redis = get_redis_connection()
    failed_attempts = redis.get('sudo_fail_{}'.format(user))
    failed_attempts = int(failed_attempts) if failed_attempts != None else 0
    if failed_attempts >= 5:
        write_log("dashboard_access", user, {"success": False, "reason": "too many attemps"})
        return render_template("dashboard/sudo.tmpl", error = True, chances = 0)

    if flask.request.method == "GET":
        return render_template("dashboard/sudo.tmpl")

    password = flask.request.form.get("password")
    if password == None:
        flask.abort(400)    

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT salt FROM users WHERE user_id = %s", (user, ))
        salt = cursor.fetchone()[0]

    finally:
        cnx.close()    

    hashed_password = hashlib.sha256((password + salt).encode()).hexdigest().upper()

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = %s AND password = %s", (user, hashed_password))
        result = cursor.fetchone()
    finally:
        cnx.close()

    if result == None:
        write_log("dashboard_access", user, {"success": False})
        redis = get_redis_connection()
        failed_attemps = int(redis.incr('sudo_fail_{}'.format(user)))
        redis.expire('sudo_fail_{}'.format(user), 300)
        ret = render_template("dashboard/sudo.tmpl", error = True, chances = max(5 - failed_attemps, 0))
        return ret
    else:
        ret = flask.make_response(flask.redirect("/dashboard/"))
        ret.set_cookie("sudo_mode", create_cookie(user))
        redis = get_redis_connection()
        redis.delete('sudo_fail_{}'.format(user))
        write_log("dashboard_access", user, {"success": True})
        return ret

@bp.route("/")
def index():
    user = check_permission()

    sudo = check_sudo(user)

    if not sudo:
        return flask.redirect("/dashboard/sudo")

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT log.type, users.name, log.data FROM log, users "
                       "WHERE users.user_id = log.operator ORDER BY log.datetime DESC LIMIT 10")
        recent_events = list(cursor)

        cursor.execute("SELECT log.datetime, log.data FROM log, users "
                       "WHERE users.user_id = log.operator AND log.operator = %s ORDER by log.datetime DESC LIMIT 10",
                       (user, ))
        recent_access = list(cursor)
    finally:
        cnx.close()
        
    return render_template("dashboard/index.tmpl", recent_events = recent_events, recent_access = recent_access,
                           log_type_to_string = log_type_to_string, log_data_simple = log_data_simple)

@bp.route("/users")
def users():
    user = check_permission()

    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    query_string = flask.request.args.get("s")

    if query_string == None:
        return render_template("dashboard/user.tmpl")

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT user_id, name, nick FROM users WHERE nick LIKE %s", ("%{}%".format(query_string), ))
        users = cursor.fetchall()
    finally:
        cnx.close()

    return render_template("dashboard/user.tmpl", users = users)

@bp.route("/userinfo/<userid>")
def userinfo(userid):
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT name, nick, email, admin FROM users WHERE user_id = %s", (userid, ))
        userinfo = cursor.fetchone()
    finally:
        cnx.close()

    if user == None:
        flask.abort(404)

    username, nick, email, admin = userinfo

    user_avatar = hashlib.md5(email.lower().strip().encode()).hexdigest().lower()

    return render_template("dashboard/userinfo.tmpl", username = username, nick = nick, email = email,
                           user_avatar = user_avatar, user_is_admin = admin, userid = userid)

@bp.route("/userinfo_update", methods=["POST"])
def userinfo_update():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    try:
        userid = flask.request.form["id"]
        nick = flask.request.form["nick"]
        email = flask.request.form["email"]
        superuser = flask.request.form["superuser"]
    except KeyError:
        flask.abort(400)

    superuser = (superuser == "true")    

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT nick, email, admin FROM users WHERE user_id = %s", (userid, ))
        oldnick, oldemail, oldadmin = cursor.fetchone()      
        cursor.execute("UPDATE users SET (nick, email, admin) = ( "
                       "%s, %s, %s ) WHERE user_id = %s", (nick, email, superuser, userid))
        cnx.commit()
    finally:
        cnx.close()
        
    log_data = {
        "operator": user,
        "original": {
            "nick": oldnick,
            "email": oldemail,
            "superuser": oldadmin
        },
        "new": {
            "nick": nick,
            "email": email,
            "superuser": superuser
        }
    }

    write_log("update_profile", user, log_data)

    return flask.redirect("/dashboard/userinfo/{}".format(userid))

@bp.route("/<operation>/<type>")
def operate(operation, type):
    user = check_permission()
    sudo = check_sudo(user)

    if not sudo:
        return flask.redirect("/dashboard/sudo")
    
    target_id = flask.request.args.get("target")
    if not target_id:
        flask.abort(400)

    hidden = True if operation == "delete" else False
    
    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("UPDATE {0} SET hidden = %s WHERE {0}_id = %s ".format(type), (hidden, target_id))
        cnx.commit()
    finally:
        cnx.close()

    referrer = "/" if type == "thread" else flask.request.referrer
    write_log(operation, user, {"type": type, "id": target_id})
    return flask.redirect(referrer)
        
@bp.route("/category")
def categories():
    user = check_permission()

    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute('SELECT category_id, name FROM category')
        categories = cursor.fetchall()
    finally:
        cnx.close()

    return render_template("dashboard/category.tmpl", categories = categories)

@bp.route("/category/new", methods=["POST"])
def categories_new():
    user = check_permission()
    sudo = check_sudo(user)

    if not sudo:
        return flask.redirect("/dashboard/sudo")

    name = flask.request.form.get("name")
    if not name:
        flask.abort(400)

    category_id = str(uuid.uuid4()).replace('-', '').upper()

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("INSERT INTO category VALUES (%s, %s)", (category_id, name))
        cnx.commit()
    finally:
        cnx.close()

    write_log("category_new", user, {"success": True, "category": name})
    return flask.redirect('/dashboard/category')
    

@bp.route("/category/merge", methods=["POST"])
def category_merge():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    try:
        src_id = flask.request.form["src"]
        dst_id = flask.request.form["dst"]
    except KeyError:
        flask.abort(400)    

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute('SELECT name FROM category WHERE category_id = %s', (src_id,))
        src_name, = cursor.fetchone()
        cursor.execute('SELECT name FROM category WHERE category_id = %s', (dst_id,))
        dst_name, = cursor.fetchone()
        
        cursor.execute('UPDATE thread SET category = %s WHERE category = %s', (dst_id, src_id))
        cursor.execute('DELETE FROM category WHERE category_id = %s', (src_id, ))
        cnx.commit()
    finally:
        cnx.close()

    log_data = {
        "src": {
            "id": src_id,
            "name": src_name
        },
        "dst": {
            "id": dst_id,
            "name": dst_name
        }
    }
    write_log("category_merge", user, log_data)
    
    return flask.redirect("/dashboard/category")

@bp.route("/threads")
def threads():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    query_string = flask.request.args.get("s")
    if query_string == None:
        return render_template("dashboard/threads.tmpl")

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT title, hidden, thread_id FROM thread WHERE title &@~ %s", (query_string, ))
        threads = cursor.fetchall()
    finally:
        cnx.close()

    return render_template("dashboard/threads.tmpl", threads = threads)

@bp.route("/threads/delete")
def thread_delete():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    thread_id = flask.request.args.get("id")
    if thread_id == None:
        flask.abort(400)

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("UPDATE thread SET hidden = TRUE WHERE thread_id = %s", (thread_id, ))
        cnx.commit()
    finally:
        cnx.close()

    return flask.redirect("/dashboard/threads")

@bp.route("/threads/restore")
def thread_restore():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    thread_id = flask.request.args.get("id")
    if thread_id == None:
        flask.abort(400)

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("UPDATE thread SET hidden = FALSE WHERE thread_id = %s", (thread_id, ))
        cnx.commit()
    finally:
        cnx.close()

    return flask.redirect("/dashboard/threads")

@bp.route("/posts")
def posts():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")
    
    return render_template("dashboard/posts.tmpl")

@bp.route("/posts/view")
def posts_view():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    return render_template("posts_view.tmpl")

@bp.route("/posts/delete")
def posts_delete():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    post_id = flask.request.args.get("id")
    if post_id == None:
        flask.abort(400)

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("UPDATE post SET hidden = TRUE WHERE post_id = %s", (post_id, ))
        cnx.commit()
    finally:
        cnx.close()

    return flask.redirect("/dashboard/posts")

@bp.route("/posts/restore")
def posts_restore():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    post_id = flask.request.args.get("/dashboard/sudo")
    if post_id == None:
        flask.abort(400)

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("UPDATE post SET hidden = FALSE WHERE post_id = %s", (post_id, ))
        cnx.commit()
    finally:
        cnx.close()

    return flask.redirect("/dashboard/posts")

@bp.route("/log")
def log():
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT log.*, users.name FROM log, users WHERE users.user_id = log.operator ORDER BY log.datetime DESC")
        logs = cursor.fetchall()
    finally:
        cnx.close()
        
    return render_template("/dashboard/logs.tmpl", logs = logs,
                           log_type_to_string = log_type_to_string,
                           log_data_simple = log_data_simple)

@bp.route("/log/detail/<id>")
def log_detail(id):
    user = check_permission()
    sudo = check_sudo(user)
    if not sudo:
        return flask.redirect("/dashboard/sudo")

    try:
        id = int(id)
    except:
        flask.abort(400)
        
    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT log.*, users.name FROM log, users WHERE users.user_id = log.operator AND log.log_id = %s", (id, ))
        details = cursor.fetchone()
    finally:
        cnx.close()

    return render_template("/dashboard/log_details.tmpl", details = details, log_type_to_string = log_type_to_string)
        

@bp.route("/logout")
def logout():
    ret = flask.make_response(flask.redirect("/"))
    ret.set_cookie("sudo_mode", "", expires=0)
    return ret
