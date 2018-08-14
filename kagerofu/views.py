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
from kagerofu.database import get_pg_connection
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
        'publish': 'publish_datetime',
        'reply': 'reply_count',
        'last_modified': 'last_modified',
        'random': 'RAND()'
    }

    category_sql = "AND thread.category = %s" if category else ''
    author_sql = "AND thread.author = %s" if author else ''

    query = (
        "SELECT thread.thread_id, thread.title, thread.datetime AS publish_datetime, "
        "users.nick, MAX(post.last_modified) AS last_modified, "
        "(SELECT COUNT(*) FROM post WHERE post.thread = thread.thread_id) AS reply_count FROM thread, post, users "
        "WHERE thread.hidden = FALSE "
        "AND post.thread = thread.thread_id "
        "AND users.user_id = thread.author "
        "AND thread.draft = %s {} {} "
        "GROUP BY thread.thread_id, users.nick "
        "ORDER BY {} DESC "
        "LIMIT {} "
        "OFFSET %s ").format(category_sql, author_sql, order_sql[order], config["paginator"]["thread_per_page"])        
    page_query = "SELECT COUNT(*) FROM thread WHERE hidden = FALSE AND draft = %s {} {}".format(category_sql, author_sql)
    category_query = "SELECT name FROM category WHERE category_id = %s"

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        page_cursor = cnx.cursor()

        if category:            
            category_cursor = cnx.cursor()

            if author:
                cursor.execute(query, (draft, category, author, (page - 1) * config["paginator"]["thread_per_page"]))
            else:
                cursor.execute(query, (draft, category, (page - 1) * config["paginator"]["thread_per_page"]))

            if author:
                page_cursor.execute(page_query, (draft, category, author))
            else:
                page_cursor.execute(page_query, (draft, category, ))
                
            category_cursor.execute(category_query, (category, ))
            
            category_name, = category_cursor.fetchone()
            
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

        total_pages, = page_cursor.fetchone()
        total_pages = int((total_pages - 1) / config["paginator"]["thread_per_page"] + 1)

        if draft:
            baseurl = "/drafts"
        elif category:
            baseurl = "/category/{}/{}".format(category, order)
        else:
            baseurl = "/index/" + order

        ret = render_template('list.tmpl', cursor = cursor, title = title, page = page, total_pages = total_pages, order = order, baseurl = baseurl)
    finally:
        cnx.close()

    return ret;

bp = flask.Blueprint("views", __name__)

@bp.route('/index/<order>/<page>')
def index(order, page):
    return list_threads(order, int(page))

@bp.route('/category/<category>/<order>/<page>')
def category_list(category, order, page):
    return list_threads(order, int(page), category)

@bp.route('/thread/view/<thread>/<page>')
def post(thread, page):
    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT title FROM thread WHERE thread_id = %s", (thread, ))
        title = cursor.fetchone()[0]

        cursor = cnx.cursor()
        cursor.execute("SELECT COUNT(*) FROM post WHERE thread = %s", (thread, ))
        post_count = cursor.fetchone()[0]

        query = (
            "SELECT post.post_id, users.nick, post.author, "
            "LOWER(MD5(TRIM(LOWER(users.email)))), "
            "post_content.content, post_content.datetime, post_content.renderer FROM post, users, thread, post_content "
            "WHERE post.thread = %s AND post.hidden = FALSE "
            "AND post.thread = thread.thread_id "
            "AND post.author = users.user_id "
            "AND post.content = post_content.content_id "
            "ORDER BY post.datetime LIMIT {} OFFSET %s".format(config["paginator"]["post_per_page"])
        )
        cursor = cnx.cursor()
        cursor.execute(query, (thread, int((int(page) - 1) * config["paginator"]["post_per_page"])))
        posts = list(cursor)

        cursor = cnx.cursor()
        cursor.execute("SELECT thread.author FROM thread WHERE thread_id = %s", (thread, ))
        thread_author_id = cursor.fetchone()[0]

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

    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()

        if edit_type == 'thread':
            cursor.execute(
                "SELECT thread.title, thread.category, thread.draft, users.admin FROM thread, users "
                "WHERE thread.thread_id = %s AND users.user_id = %s AND (thread.author = users.user_id OR users.admin = TRUE)",
                (target_id, user)
            )
            title, category, is_draft, _ = cursor.fetchone()

            cursor.execute("SELECT post.post_id, users.admin FROM post, users "
                           "WHERE post.thread = %s AND users.user_id = %s AND (post.author = users.user_id OR users.admin = TRUE) "
                           "ORDER BY datetime LIMIT 1 OFFSET 0",
                           (target_id, user))
            post_id = cursor.fetchone()
            if not post_id:
                flask.abort(404)
            post_id = post_id[0]
        else:
            post_id = target_id
    except:
        cnx.close()
        raise
        
    try:
        cursor = cnx.cursor()
        cursor.execute("SELECT content, renderer FROM post_content WHERE post = %s ORDER BY datetime DESC LIMIT 1 OFFSET 0", (post_id, ))
        content, renderer = cursor.fetchone()
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
        kwargs["title"] = "Reply Edit"
        
    return render_template("edit.tmpl", **kwargs)
