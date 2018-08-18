import flask
import json

with open("config.json") as f:
    config = json.load(f)

from kagerofu.views import bp as views_bp
from kagerofu.action import bp as action_bp
from kagerofu.admin import bp as admin_bp

app = flask.Flask(__name__)
app.jinja_env.line_statement_prefix = "#"
app.jinja_env.line_comment_prefix = "///"

app.register_blueprint(views_bp)
app.register_blueprint(action_bp)
app.register_blueprint(admin_bp, url_prefix="/dashboard")
