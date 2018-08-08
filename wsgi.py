import flask
import json
import mysql.connector
import misaka
import html
import re
import hashlib

with open("config.json") as f:
    config = json.load(f)

app = flask.Flask(__name__)
app.jinja_env.line_statement_prefix = "#"
app.jinja_env.line_comment_prefix = "///"

def get_mysql_connection():
    return mysql.connector.connect(pool_name = "kagerou", **config["db"])

def render_template(template, **kwargs):
    args = {
        "title": "How do your end up here?",
        "body": "How do your end up here?"
    }
        
    try:
        cnx = get_mysql_connection()
        cursor = cnx.cursor()
        cursor.execute('SELECT name, HEX(id) FROM Category ORDER BY id')
        categories = list(cursor)

    finally:
        cnx.close()

    kwargs["categories"] = categories

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
        return lines.join("")

    if renderer == "markdown":
        return renderer_markdown(content)
    else:
        return renderer_plain(content)

def create_cookie(user):
    cookie_hash = hashlib.sha256((user + config["cookie_key"]).encode("utf8")).hexdigest()
    cookie = "{}|{}".format(user, cookie_hash)
    return cookie

def test_cookie(cookie):
    user, hash = cookie.rsplit('|')
    cookie_hash = hashlib.sha256((user + config["cookie_key"]).encode("utf8")).hexdigest()
    return hashlib.sha256((user + config["cookie_key"]).encode("utf8")).hexdigest() == hash
        
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

    try:
        cnx = mysql.connector.connect(pool_name = "kagerou", **config["db"])
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
    try:
        cnx = get_mysql_connection()
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
                           render_content = render_content, title = title)
