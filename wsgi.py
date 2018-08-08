import flask
import json
import mysql.connector
import misaka
import html
import re
import hashlib
import datetime
import uuid

with open("config.json") as f:
    config = json.load(f)

app = flask.Flask(__name__)
app.jinja_env.line_statement_prefix = "#"
app.jinja_env.line_comment_prefix = "///"

def get_mysql_connection():
    return mysql.connector.connect(pool_name = "kagerofu", **config["db"])

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

    return flask.render_template(template, **kwargs)

def render_content(renderer, content):
    def renderer_markdown(content):
        def escape_formula(formula):
            return re.sub(r"([_*\\{}()])", r"\\\1", formula, flags=re.M)

        def remove_unnecessary_slash(formula):
            return re.sub(r"\\([_*\\{}()])", r"\1", formula, flags=re.M)

        # content = content.replace("\n", "\n\n")
        # content = re.sub(r"(```(.*?)```)", lambda m: m.group(1).replace("\n\n", "\n"), content, flags=re.M)
        content = re.sub(r"(\\\((.+?)\\\))", lambda m: escape_formula(m.group(1)), content, flags=re.M)
        content = re.sub(r"(\$(.+?)\$)", lambda m: escape_formula(m.group(1)), content, flags=re.M)
        content = re.sub(r"```math(.*?)```", r"\1", content, flags=re.M)

        content = misaka.html(content, ( 'fenced-code', 'strikethrough' ), ( 'html-escape', ))

        content = re.sub(r'(\\\((.+?)\\\))', lambda m: remove_unnecessary_slash(m.group(1)), content, flags=re.M)
        content = re.sub(r'(\$(.+?)\$)', lambda m: remove_unnecessary_slash(m.group(1)), content, flags=re.M)
        
        return content

    def renderer_plain(content):
        content = html.escape(content)
        lines = content.split("\n")
        lines = map(lambda x: "<p>{}</p>".format(x), lines)
        return "".join(lines)

    if renderer == "markdown":
        return renderer_markdown(content)
    else:
        return renderer_plain(content)

def create_cookie(user):
    cookie_hash = hashlib.sha256((user + config["cookie_key"]).encode("utf8")).hexdigest()
    cookie = "{}|{}".format(user, cookie_hash)
    return cookie

def read_cookie(cookie):
    user, hashval = cookie.rsplit('|')
    cookie_hash = hashlib.sha256((user + config["cookie_key"]).encode("utf8")).hexdigest()
    if hashlib.sha256((user + config["cookie_key"]).encode("utf8")).hexdigest() == hashval:
        return user
    else:
        return None
        
def list_threads(order, page, category = None):
    order_sql = {
        'publish': 'UNIX_TIMESTAMP(publish_datetime)',
        'reply': 'reply_count',
        'last_modified': 'last_modified',
        'random': 'RAND()'
    }

    category_sql = "AND Thread.category = UNHEX(%s)" if category else ''

    query = (
        "SELECT HEX(Thread.id) AS tid, Thread.title, Thread.datetime as publish_datetime, "
        "User.name AS author, MAX(Post.last_modified) AS last_modified, "
        "(SELECT COUNT(*) FROM Post WHERE Post.thread = Thread.id) AS reply_count FROM Thread "
        "INNER JOIN User ON User.id = Thread.author "
        "INNER JOIN Post ON Post.thread = Thread.id AND Post.hidden = FALSE "
        "WHERE Thread.hidden = FALSE AND Thread.draft = FALSE {} "
        "GROUP BY Thread.id "
        "ORDER BY {} DESC "
        "LIMIT %s, {}").format(category_sql, order_sql[order], config["paginator"]["thread_per_page"])        
    page_query = "SELECT COUNT(*) FROM Thread WHERE hidden = FALSE AND draft = FALSE " + category_sql
    category_query = "SELECT name FROM Category WHERE id = UNHEX(%s)"

    cnx = mysql.connector.connect(pool_name = "kagerou", **config["db"])
    try:
        cursor = cnx.cursor(buffered=True)
        page_cursor = cnx.cursor(buffered=True)

        if category:            
            category_cursor = cnx.cursor(buffered=True)

            cursor.execute(query, (category, (page - 1) * config["paginator"]["thread_per_page"]))
            page_cursor.execute(page_query, (category, ))
            category_cursor.execute(category_query, (category, ))
            
            category_name, = category_cursor.next()
            
            title = "Category: " + category_name

        else:
            cursor.execute(query, ((page - 1) * config["paginator"]["thread_per_page"], ))
            page_cursor.execute(page_query)

            title = "Index"

        total_pages, = page_cursor.next()
        total_pages = int((total_pages - 1) / config["paginator"]["thread_per_page"] + 1)
    finally:
        cnx.close()

    baseurl = "/category/" + category if category else "/index"
    
    return render_template('list.tmpl', cursor = cursor, title = title, page = page, total_pages = total_pages, order = order, baseurl = baseurl)

@app.route('/index/<order>/<page>')
def index(order, page):
    return list_threads(order, int(page))

@app.route('/category/<category>/<order>/<page>')
def category_list(category, order, page):
    return list_threads(order, int(page), category)

@app.route('/thread/view/<thread>/<page>')
def post(thread, page):
    cnx = get_mysql_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT title FROM Thread WHERE id = UNHEX(%s)", (thread, ))
        title = cursor.next()[0]

        cursor = cnx.cursor()
        cursor.execute("SELECT COUNT(*) FROM Post WHERE thread = UNHEX(%s)", (thread, ))
        post_count = cursor.next()[0]

        query = (
            "SELECT HEX(Post.id) AS pid, User.name AS author, "
            "HEX(Post.author) AS author_id, "
            "LOWER(MD5(TRIM(LOWER(User.email)))) AS avatar, "
            "PostContent.content, PostContent.datetime, PostContent.renderer FROM Post "
            "INNER JOIN User ON User.id = Post.author "
            "INNER JOIN Thread ON Thread.id = Post.thread "
            "INNER JOIN PostContent ON PostContent.id = Post.content "
            "WHERE Post.thread = UNHEX(%s) AND Post.hidden = FALSE "
            "ORDER BY Post.datetime LIMIT %s, {}".format(config["paginator"]["post_per_page"])
        )
        cursor = cnx.cursor()
        cursor.execute(query, (thread, int((int(page) - 1) / config["paginator"]["post_per_page"])))
        posts = list(cursor)

        cursor = cnx.cursor()
        cursor.execute("SELECT HEX(Thread.author) FROM Thread WHERE id = UNHEX(%s)", (thread, ))
        thread_author_id = cursor.next()[0]

    finally:
        cnx.close()
        
    total_pages = int((post_count - 1) / config["paginator"]["post_per_page"])
    return render_template("post.tmpl", posts = posts,
                           page = int(page), total_pages = total_pages,
                           thread_author_id = thread_author_id,
                           baseurl = "/thread/view/{}".format(thread), post_per_page = config["paginator"]["post_per_page"],
                           render_content = render_content, title = title, thread_id = thread)

@app.route('/login', methods=['GET', 'POST'])
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

@app.route('/logout')
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

@app.route('/new')
def new():
    cnx = get_mysql_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT HEX(id), name FROM Category")
        category_list = list(cursor)
        
    finally:
        cnx.close()

    return render_template("new.tmpl", title = "New Thread", categories = category_list)

@app.route('/action/new_thread', methods=['POST'])
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
    is_draft = bool(flask.request.form["draft"])

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

@app.route('/action/reply', methods=['POST'])
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


