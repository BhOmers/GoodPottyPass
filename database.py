import sqlite3
from config import DB_FILE
import os


def get_conn():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS card_registry (
                uid TEXT PRIMARY KEY,
                card_number INTEGER UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_number INTEGER NOT NULL,
                name TEXT NOT NULL,
                period INTEGER NOT NULL,
                UNIQUE(card_number, period)
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                period INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'absent',
                scan_time TEXT,
                UNIQUE(student_id, date, period),
                FOREIGN KEY(student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS bathroom_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                period INTEGER NOT NULL,
                out_time TEXT NOT NULL,
                in_time TEXT,
                duration_minutes REAL,
                FOREIGN KEY(student_id) REFERENCES students(id)
            );

            CREATE TABLE IF NOT EXISTS bathroom_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                period INTEGER NOT NULL,
                queued_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id)
            );
        """)


# ── Card Registry ─────────────────────────────────────────────────────────────

def register_card(uid, card_number):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO card_registry (uid, card_number) VALUES (?,?)",
            (uid, card_number),
        )


def get_card_number(uid):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT card_number FROM card_registry WHERE uid=?", (uid,)
        ).fetchone()
        return row["card_number"] if row else None


def get_all_card_registrations():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM card_registry ORDER BY card_number"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_card_registration(card_number):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM card_registry WHERE card_number=?", (card_number,)
        )


# ── Students ──────────────────────────────────────────────────────────────────

def get_student(card_number, period):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE card_number=? AND period=?",
            (card_number, period),
        ).fetchone()
        return dict(row) if row else None


def get_all_students(period=None):
    with get_conn() as conn:
        if period is not None:
            rows = conn.execute(
                "SELECT * FROM students WHERE period=? ORDER BY card_number",
                (period,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM students ORDER BY period, card_number"
            ).fetchall()
        return [dict(r) for r in rows]


def add_student(card_number, name, period):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO students (card_number, name, period) VALUES (?,?,?)",
            (card_number, name, period),
        )


def delete_student(student_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM students WHERE id=?", (student_id,))


def clear_roster(period):
    with get_conn() as conn:
        conn.execute("DELETE FROM students WHERE period=?", (period,))


# ── Attendance ────────────────────────────────────────────────────────────────

def get_attendance(date, period):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.card_number, s.name, s.period,
                   COALESCE(a.status, 'absent') AS status,
                   a.scan_time
            FROM students s
            LEFT JOIN attendance a
                ON s.id = a.student_id AND a.date=? AND a.period=?
            WHERE s.period=?
            ORDER BY s.card_number
            """,
            (date, period, period),
        ).fetchall()
        return [dict(r) for r in rows]


def get_student_attendance_status(student_id, date, period):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT status FROM attendance WHERE student_id=? AND date=? AND period=?",
            (student_id, date, period),
        ).fetchone()
        return row["status"] if row else None


def mark_attendance(student_id, date, period, status, scan_time):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO attendance (student_id, date, period, status, scan_time)
            VALUES (?,?,?,?,?)
            ON CONFLICT(student_id, date, period) DO UPDATE SET
                status=excluded.status,
                scan_time=COALESCE(excluded.scan_time, scan_time)
            """,
            (student_id, date, period, status, scan_time),
        )


def manual_status_change(student_id, date, period, new_status):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO attendance (student_id, date, period, status, scan_time)
            VALUES (?,?,?,?,NULL)
            ON CONFLICT(student_id, date, period) DO UPDATE SET status=excluded.status
            """,
            (student_id, date, period, new_status),
        )


# ── Bathroom ──────────────────────────────────────────────────────────────────

def get_current_bathroom_out(date, period):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT bs.*, s.name, s.card_number
            FROM bathroom_sessions bs
            JOIN students s ON s.id = bs.student_id
            WHERE bs.date=? AND bs.period=? AND bs.in_time IS NULL
            ORDER BY bs.out_time DESC LIMIT 1
            """,
            (date, period),
        ).fetchone()
        return dict(row) if row else None


def start_bathroom_session(student_id, date, period, out_time):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO bathroom_sessions (student_id, date, period, out_time) VALUES (?,?,?,?)",
            (student_id, date, period, out_time),
        )


def end_bathroom_session(student_id, date, period, in_time, duration_minutes):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE bathroom_sessions
            SET in_time=?, duration_minutes=?
            WHERE student_id=? AND date=? AND period=? AND in_time IS NULL
            """,
            (in_time, duration_minutes, student_id, date, period),
        )


def get_bathroom_queue(date, period):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT bq.*, s.name, s.card_number
            FROM bathroom_queue bq
            JOIN students s ON s.id = bq.student_id
            WHERE bq.date=? AND bq.period=?
            ORDER BY bq.queued_at ASC
            """,
            (date, period),
        ).fetchall()
        return [dict(r) for r in rows]


def add_to_bathroom_queue(student_id, date, period, queued_at):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM bathroom_queue WHERE student_id=? AND date=? AND period=?",
            (student_id, date, period),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO bathroom_queue (student_id, date, period, queued_at) VALUES (?,?,?,?)",
                (student_id, date, period, queued_at),
            )
            return True
        return False


def remove_from_bathroom_queue(student_id, date, period):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM bathroom_queue WHERE student_id=? AND date=? AND period=?",
            (student_id, date, period),
        )


def get_bathroom_log(date=None, period=None):
    with get_conn() as conn:
        query = """
            SELECT bs.*, s.name, s.card_number
            FROM bathroom_sessions bs
            JOIN students s ON s.id = bs.student_id
            WHERE 1=1
        """
        params = []
        if date:
            query += " AND bs.date=?"
            params.append(date)
        if period is not None:
            query += " AND bs.period=?"
            params.append(period)
        query += " ORDER BY bs.out_time DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def force_return_bathroom(student_id, date, period, in_time, duration_minutes):
    end_bathroom_session(student_id, date, period, in_time, duration_minutes)
    remove_from_bathroom_queue(student_id, date, period)


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_bathroom_total_minutes(student_id, start_date=None, end_date=None):
    """Total completed bathroom minutes for a student, optionally filtered by date range."""
    with get_conn() as conn:
        query = """
            SELECT COALESCE(SUM(duration_minutes), 0) AS total,
                   COUNT(*) AS trips
            FROM bathroom_sessions
            WHERE student_id=? AND duration_minutes IS NOT NULL
        """
        params = [student_id]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        row = conn.execute(query, params).fetchone()
        total = round(row["total"], 1) if row else 0.0
        trips = row["trips"] if row else 0
        avg   = round(total / trips, 1) if trips > 0 else 0.0
        return {"total_minutes": total, "trips": trips, "avg_minutes": avg}


def get_all_bathroom_analytics(period=None, start_date=None, end_date=None):
    """
    Returns per-student analytics for the given filters.
    Each row: student_id, card_number, name, period, total_minutes, trips, avg_minutes
    """
    with get_conn() as conn:
        query = """
            SELECT s.id AS student_id, s.card_number, s.name, s.period,
                   COALESCE(SUM(bs.duration_minutes), 0) AS total_minutes,
                   COUNT(bs.id) AS trips
            FROM students s
            LEFT JOIN bathroom_sessions bs
                ON s.id = bs.student_id
                AND bs.duration_minutes IS NOT NULL
        """
        params = []
        wheres = []

        if start_date:
            wheres.append("(bs.date IS NULL OR bs.date >= ?)")
            params.append(start_date)
        if end_date:
            wheres.append("(bs.date IS NULL OR bs.date <= ?)")
            params.append(end_date)
        if period is not None:
            wheres.append("s.period = ?")
            params.append(period)

        if wheres:
            query += " WHERE " + " AND ".join(wheres)

        query += " GROUP BY s.id ORDER BY total_minutes DESC"
        rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["total_minutes"] = round(d["total_minutes"], 1)
            d["avg_minutes"] = round(d["total_minutes"] / d["trips"], 1) if d["trips"] > 0 else 0.0
            results.append(d)
        return results


def get_bathroom_weekly_trend(student_id, start_date, end_date):
    """
    Returns weekly aggregated bathroom minutes for trend charts.
    Each row: week_start (YYYY-MM-DD Monday), total_minutes, trips
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                date(date, 'weekday 0', '-6 days') AS week_start,
                COALESCE(SUM(duration_minutes), 0) AS total_minutes,
                COUNT(*) AS trips
            FROM bathroom_sessions
            WHERE student_id=?
              AND duration_minutes IS NOT NULL
              AND date >= ? AND date <= ?
            GROUP BY week_start
            ORDER BY week_start ASC
            """,
            (student_id, start_date, end_date),
        ).fetchall()
        return [dict(r) for r in rows]


def get_bathroom_daily_trend(start_date, end_date, period=None):
    """
    Class-wide daily bathroom usage trend (total trips per day).
    """
    with get_conn() as conn:
        query = """
            SELECT bs.date,
                   COUNT(*) AS trips,
                   COALESCE(SUM(bs.duration_minutes), 0) AS total_minutes
            FROM bathroom_sessions bs
            JOIN students s ON s.id = bs.student_id
            WHERE bs.duration_minutes IS NOT NULL
              AND bs.date >= ? AND bs.date <= ?
        """
        params = [start_date, end_date]
        if period is not None:
            query += " AND s.period = ?"
            params.append(period)
        query += " GROUP BY bs.date ORDER BY bs.date ASC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_student_by_id(student_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE id=?", (student_id,)
        ).fetchone()
        return dict(row) if row else None
