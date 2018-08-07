import mysql.connector
import json

from flask import Flask, render_template

with open("config.json") as f:
    config = json.load(f)
    
app = Flask(__name__)
app.jinja_env.line_statement_prefix = "#"

def list_posts(order, page, category = None):
    order_sql = {
        'publish': 'UNIX_TIMESTAMP(publish_datetime)',
        'reply': 'reply_count',
        'last_modified': 'last_modified',
        'random': 'RAND()'
    }

    category_sql = "AND THREAD.category = UNHEX(%s)" if category else ''

    try :
        cnx = mysql.connector.connect(pool_name = "kagerou", **config["db"])
        
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

        cursor = cnx.cursor(buffered=True)
        page_cursor = cnx.cursor(buffered=True)

        if category:
            category_query = "SELECT name FROM Category WHERE id = UNHEX(%s)"
            
            category_cursor = cnx.cursor(buffered=True)

            cursor.execute(query, (category, (page - 1) * config["paginator"]["thread_per_page"]))
            page_cursor.execute(page_query, (category, ))
            category_cursor.execute(category_query, (category, 1))
            
            category_name, = category_cursor.next()
            
            title = "Category: " + category.name

        else:
            cursor.execute(query, ((page - 1) * config["paginator"]["thread_per_page"], ))
            page_cursor.execute(page_query)

            title = "Index"

        total_pages, = page_cursor.next()
        total_pages = int((total_pages - 1) / config["paginator"]["thread_per_page"] + 1)

        baseurl = "/category/" + category if category else "/index"
    
        return render_template('list.tmpl', cursor = cursor, title = title, page = page, total_pages = total_pages, order = order, baseurl = baseurl)

    finally:
        cnx.close()

@app.route('/index/<order>/<page>')
def index(order, page):
    return list_posts(order, int(page))
