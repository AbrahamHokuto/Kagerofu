import platform

if platform.python_implementation() == 'PyPy':
    import psycopg2cffi as psycopg2
else:
    import psycopg2

from kagerofu import config

def get_pg_connection():
    return psycopg2.connect(**config["db"])
