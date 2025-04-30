import os
import sqlite3
import psycopg2
from urllib.parse import urlparse

DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

def get_db_connection():
    if USE_POSTGRES:
        result = urlparse(DATABASE_URL)
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port
        return psycopg2.connect(
            dbname=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
    else:
        return sqlite3.connect("bot_data.db")

def execute_query(query, params=None, fetch=False, many=False):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if USE_POSTGRES:
            query = query.replace("?", "%s")
        if params is None:
            cursor.execute(query)
        elif many:
            cursor.executemany(query, params)
        else:
            cursor.execute(query, params)
        result = cursor.fetchall() if fetch else None
        conn.commit()
        return result

def init_db():
    execute_query('''
        CREATE TABLE IF NOT EXISTS guild_setup (
            guild_id BIGINT PRIMARY KEY,
            guild_token TEXT,
            guild_name TEXT,
            discord_role TEXT,
            server TEXT
        )
    ''')
    execute_query('''
        CREATE TABLE IF NOT EXISTS user_data (
            guild_id BIGINT,
            user_id BIGINT,
            ign TEXT,
            PRIMARY KEY (guild_id, user_id)
        )
    ''')

def load_guild_setup(guild_id):
    result = execute_query("SELECT guild_token, guild_name, discord_role, server FROM guild_setup WHERE guild_id = ?", (guild_id,), fetch=True)
    row = result[0] if result else [None, None, None, None]
    return {
        "guild_token": row[0],
        "guild_name": row[1],
        "discord_role": row[2],
        "server": row[3] or os.getenv("SERVER", "Asia")
    }

def save_guild_setup(guild_id, data):
    execute_query(
        """
        INSERT INTO guild_setup (guild_id, guild_token, guild_name, discord_role, server)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (guild_id) DO UPDATE SET
            guild_token = EXCLUDED.guild_token,
            guild_name = EXCLUDED.guild_name,
            discord_role = EXCLUDED.discord_role,
            server = EXCLUDED.server
        """,
        (guild_id, data["guild_token"], data["guild_name"], data["discord_role"], data["server"])
    )

def load_user_data(guild_id):
    result = execute_query("SELECT user_id, ign FROM user_data WHERE guild_id = ?", (guild_id,), fetch=True)
    return {row[0]: {"ign": row[1]} for row in result}

def save_user_data(guild_id, user_data):
    execute_query("DELETE FROM user_data WHERE guild_id = ?", (guild_id,))
    records = [(guild_id, uid, data["ign"]) for uid, data in user_data.items()]
    execute_query("INSERT INTO user_data (guild_id, user_id, ign) VALUES (?, ?, ?)", records, many=True)
