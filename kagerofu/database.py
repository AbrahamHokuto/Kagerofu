import platform

if platform.python_implementation() == 'PyPy':
    import psycopg2cffi as psycopg2
    import psycopg2cffi.extras as psycopg2extras
else:
    import psycopg2
    import psycopg2.extras as psycopg2extras

import redis

from kagerofu import config

def get_pg_connection():
    return psycopg2.connect(**config["postgre"])

def get_redis_connection():
    return redis.Redis(**config["redis"])

def json_wrapper(value):
    return psycopg2extras.Json(value)
