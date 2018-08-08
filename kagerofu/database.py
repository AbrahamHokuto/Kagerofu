import mysql.connector

from kagerofu import config

def get_mysql_connection():
    return mysql.connector.connect(pool_name = "kagerofu", **config["db"])
