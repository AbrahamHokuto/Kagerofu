import psycopg2

from kagerofu import config

def get_pg_connection():
    return psycopg2.connect(**config["db"])
