import flask
import misaka
import hashlib
import re
import html
import pygments
import pygments.util
import pygments.formatters
import pygments.lexers
import pygments.styles

from kagerofu.cookie import read_cookie, create_cookie
from kagerofu.database import get_mysql_connection
from kagerofu.template import render_template
from kagerofu import config

def render_content(renderer, content):
    def renderer_markdown(content):
        class HighlighterRenderer(misaka.HtmlRenderer):
            def blockcode(self, text, lang):
                text = text.replace('\n\n', '\n')
                try:
                    lexer = pygments.lexers.get_lexer_by_name(lang, stripall=True)
                except pygments.util.ClassNotFound:
                    try:
                        lexer = pygments.lexers.guess_lexer(text)
                    except pygments.util.ClassNotFound:
                        lexer = None

                if lexer:
                    formatter = pygments.formatters.HtmlFormatter()
                    return pygments.highlight(text, lexer, formatter)

                return '\n<pre><code>{}</code></pre>\n'.format(html.escape(text.strip()))
                        
        def escape_formula(formula):
            return re.sub(r"([_*\\{}()])", r"\\\1", formula, flags=re.M)

        def remove_unnecessary_slash(formula):
            return re.sub(r"\\([_*\\{}()])", r"\1", formula, flags=re.M)

        content = content.replace("\n", "\n\n")
        content = re.sub(r"(\\\((.+?)\\\))", lambda m: escape_formula(m.group(1)), content, flags=re.M)
        content = re.sub(r"(\$(.+?)\$)", lambda m: escape_formula(m.group(1)), content, flags=re.M)
        content = re.sub(r"```math(.*?)```", r"\1", content, flags=re.M)

        renderer = HighlighterRenderer(("escape", ))
        markdown = misaka.Markdown(renderer, ( 'fenced-code', 'strikethrough' ))

        content = markdown(content)

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

def list_threads(order, page, category = None, author = None, draft = False):
    order_sql = {
        'publish': 'UNIX_TIMESTAMP(publish_datetime)',
        'reply': 'reply_count',
        'last_modified': 'last_modified',
        'random': 'RAND()'
    }

    category_sql = "AND Thread.category = UNHEX(%s)" if category else ''
    author_sql = "AND Thread.author = UNHEX(%s)" if author else ''

    query = (
        "SELECT HEX(Thread.id) AS tid, Thread.title, Thread.datetime as publish_datetime, "
        "User.name AS author, MAX(Post.last_modified) AS last_modified, "
        "(SELECT COUNT(*) FROM Post WHERE Post.thread = Thread.id) AS reply_count FROM Thread "
        "INNER JOIN User ON User.id = Thread.author "
        "INNER JOIN Post ON Post.thread = Thread.id AND Post.hidden = FALSE "
        "WHERE Thread.hidden = FALSE AND Thread.draft = %s {} {}"
        "GROUP BY Thread.id "
        "ORDER BY {} DESC "
        "LIMIT %s, {}").format(category_sql, author_sql, order_sql[order], config["paginator"]["thread_per_page"])        
    page_query = "SELECT COUNT(*) FROM Thread WHERE hidden = FALSE AND draft = %s {} {}".format(category_sql, author_sql)
    category_query = "SELECT name FROM Category WHERE id = UNHEX(%s)"

    cnx = get_mysql_connection()
    try:
        cursor = cnx.cursor(buffered=True)
        page_cursor = cnx.cursor(buffered=True)

        if category:            
            category_cursor = cnx.cursor(buffered=True)

            if author:
                cursor.execute(query, (draft, category, author, (page - 1) * config["paginator"]["thread_per_page"]))
            else:
                cursor.execute(query, (draft, category, (page - 1) * config["paginator"]["thread_per_page"]))

            if author:
                page_cursor.execute(page_query, (draft, category, author))
            else:
                page_cursor.execute(page_query, (draft, category, ))
                
            category_cursor.execute(category_query, (category, ))
            
            category_name, = category_cursor.next()
            
            title = "Category: " + category_name

        else:
            if author:
                cursor.execute(query, (draft, author, (page - 1) * config["paginator"]["thread_per_page"]))
            else:
                cursor.execute(query, (draft, (page - 1) * config["paginator"]["thread_per_page"]))

            if author:
                page_cursor.execute(page_query, (draft, author))
            else:
                page_cursor.execute(page_query, (draft, ))

            title = "Index"

        total_pages, = page_cursor.next()
        total_pages = int((total_pages - 1) / config["paginator"]["thread_per_page"] + 1)
    finally:
        cnx.close()

        if draft:
            baseurl = "/drafts"
        elif category:
            baseurl = "/category/{}/{}".format(category, order)
        else:
            baseurl = "/index/" + order

    return render_template('list.tmpl', cursor = cursor, title = title, page = page, total_pages = total_pages, order = order, baseurl = baseurl)

bp = flask.Blueprint("views", __name__)

@bp.route('/index/<order>/<page>')
def index(order, page):
    return list_threads(order, int(page))

@bp.route('/category/<category>/<order>/<page>')
def category_list(category, order, page):
    return list_threads(order, int(page), category)

@bp.route('/thread/view/<thread>/<page>')
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
        cursor.execute(query, (thread, int((int(page) - 1) * config["paginator"]["post_per_page"])))
        posts = list(cursor)

        cursor = cnx.cursor()
        cursor.execute("SELECT HEX(Thread.author) FROM Thread WHERE id = UNHEX(%s)", (thread, ))
        thread_author_id = cursor.next()[0]

    finally:
        cnx.close()
        
    total_pages = int((post_count - 1) / config["paginator"]["post_per_page"] + 1)
    return render_template("post.tmpl", posts = posts,
                           page = int(page), total_pages = total_pages,
                           thread_author_id = thread_author_id,
                           baseurl = "/thread/view/{}".format(thread), post_per_page = config["paginator"]["post_per_page"],
                           render_content = render_content, title = title, thread_id = thread)

@bp.route('/drafts/<order>/<page>')
def drafts(order, page):
    try:
        user = read_cookie(flask.request.cookies["session"])
    except:
        user = None
        
    if user == None:
        return flask.redirect("/")
    
    return list_threads(order, int(page), author = user, draft = True)

@bp.route('/<edit_type>/edit/<target_id>')
def edit(edit_type, target_id):
    try:
        user = read_cookie(flask.request.cookies["session"])
    except:
        user = None
        
    if user == None:
        flask.abort(401)

    cnx = get_mysql_connection()
    try:
        cursor = cnx.cursor()

        if edit_type == 'thread':
            cursor.execute(
                "SELECT title, HEX(category), draft FROM Thread "
                "WHERE id = UNHEX(%s) AND author = UNHEX(%s)",
                (target_id, user)
            )
            title, category, is_draft = cursor.next()

            cursor.execute("SELECT HEX(id) FROM Post WHERE Post.thread = UNHEX(%s) ORDER BY datetime LIMIT 0, 1",
                           (target_id, ))
            post_id = cursor.next()[0]
        else:
            post_id = target_id
    except StopIteration:
        cnx.close()
        flask.abort(404)
    except:
        cnx.close()
        raise
        
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT content, renderer FROM PostContent WHERE post = UNHEX(%s) ORDER BY datetime DESC LIMIT 0, 1", (post_id, ))
        content, renderer = cursor.next()
    finally:
        cnx.close()

    kwargs = {
        "renderer": renderer,
        "referrer": flask.request.referrer,
        "content": content,
        "post_id": post_id
    }
    
    if edit_type == "thread":
        print(title)
        kwargs["type"] = "edit_thread"
        kwargs["title"] = title
        kwargs["current_category_id"] = category
        kwargs["draft"] = is_draft
        kwargs["thread_id"] = target_id
    else:
        kwargs["type"] = "edit_post"
        
    return render_template("edit.tmpl", **kwargs)
