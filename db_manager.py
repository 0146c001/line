import sqlite3
import json
import os

DB_PATH = 'events.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # Create events table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                event_date TEXT NOT NULL,
                event_time TEXT NOT NULL,
                location TEXT,
                start_time_dt TEXT NOT NULL,
                google_event_id TEXT,
                reminded INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Create sessions table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                pending_event TEXT
            )
        ''')
        conn.commit()

def save_session(user_id, state, pending_event):
    pending_event_str = json.dumps(pending_event, ensure_ascii=False) if pending_event else None
    with get_db() as conn:
        conn.execute('''
            INSERT INTO user_sessions (user_id, state, pending_event)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                state = excluded.state,
                pending_event = excluded.pending_event
        ''', (user_id, state, pending_event_str))
        conn.commit()

def get_session(user_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM user_sessions WHERE user_id = ?', (user_id,)).fetchone()
        if row:
            return {
                'user_id': row['user_id'],
                'state': row['state'],
                'pending_event': json.loads(row['pending_event']) if row['pending_event'] else None
            }
        return None

def clear_session(user_id):
    with get_db() as conn:
        conn.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))
        conn.commit()

def add_event(user_id, summary, event_date, event_time, location, start_time_dt, google_event_id=None):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO events (user_id, summary, event_date, event_time, location, start_time_dt, google_event_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, summary, event_date, event_time, location, start_time_dt, google_event_id))
        conn.commit()
        return cursor.lastrowid

def get_upcoming_unreminded_events(minutes_limit=90):
    import datetime
    from zoneinfo import ZoneInfo
    taipei_tz = ZoneInfo("Asia/Taipei")
    now_taipei = datetime.datetime.now(taipei_tz)
    threshold = now_taipei + datetime.timedelta(minutes=minutes_limit)
    past_limit = now_taipei - datetime.timedelta(minutes=30) # Don't remind for events that started more than 30 mins ago
    
    threshold_str = threshold.strftime("%Y-%m-%d %H:%M:%S")
    past_limit_str = past_limit.strftime("%Y-%m-%d %H:%M:%S")
    
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM events
            WHERE reminded = 0
              AND start_time_dt <= ?
              AND start_time_dt >= ?
        ''', (threshold_str, past_limit_str)).fetchall()
        return [dict(row) for row in rows]

def acquire_reminder_lock(event_id):
    with get_db() as conn:
        cursor = conn.execute('UPDATE events SET reminded = 1 WHERE id = ? AND reminded = 0', (event_id,))
        conn.commit()
        return cursor.rowcount > 0
