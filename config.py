import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
DB_FILE = os.path.join(DATA_DIR, "attendance.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

# ── Default Schedule Presets ──────────────────────────────────────────────────
# Each preset defines which periods are active and their start/end times.
# active_periods controls which period numbers run that day (block schedule support).

DEFAULT_SCHEDULES = {
    "regular_block_a": {
        "name": "Regular Block A",
        "active_periods": [0, 1, 3, 5],
        "periods": {
            "0": {"start": "07:00", "end": "07:50"},
            "1": {"start": "08:00", "end": "09:30"},
            "3": {"start": "09:40", "end": "11:10"},
            "5": {"start": "12:00", "end": "13:30"},
        },
    },
    "regular_block_b": {
        "name": "Regular Block B",
        "active_periods": [0, 2, 4, 6],
        "periods": {
            "0": {"start": "07:00", "end": "07:50"},
            "2": {"start": "08:00", "end": "09:30"},
            "4": {"start": "09:40", "end": "11:10"},
            "6": {"start": "12:00", "end": "13:30"},
        },
    },
    "minimum_day_plc": {
        "name": "Minimum Day (PLC)",
        "active_periods": [0, 1, 2, 3, 4, 5, 6],
        "periods": {
            "0": {"start": "07:00", "end": "07:35"},
            "1": {"start": "07:45", "end": "08:20"},
            "2": {"start": "08:30", "end": "09:05"},
            "3": {"start": "09:15", "end": "09:50"},
            "4": {"start": "10:00", "end": "10:35"},
            "5": {"start": "10:45", "end": "11:20"},
            "6": {"start": "11:30", "end": "12:05"},
        },
    },
    "minimum_day_assembly": {
        "name": "Minimum Day (Assembly)",
        "active_periods": [0, 1, 2, 3, 4, 5, 6],
        "periods": {
            "0": {"start": "07:00", "end": "07:35"},
            "1": {"start": "07:45", "end": "08:20"},
            "2": {"start": "08:30", "end": "09:05"},
            "3": {"start": "09:15", "end": "09:50"},
            "4": {"start": "10:00", "end": "10:35"},
            "5": {"start": "10:45", "end": "11:20"},
            "6": {"start": "11:30", "end": "12:05"},
        },
    },
    "minimum_day_staff_pd": {
        "name": "Minimum Day (Staff PD)",
        "active_periods": [0, 1, 2, 3, 4, 5, 6],
        "periods": {
            "0": {"start": "07:00", "end": "07:35"},
            "1": {"start": "07:45", "end": "08:20"},
            "2": {"start": "08:30", "end": "09:05"},
            "3": {"start": "09:15", "end": "09:50"},
            "4": {"start": "10:00", "end": "10:35"},
            "5": {"start": "10:45", "end": "11:20"},
            "6": {"start": "11:30", "end": "12:05"},
        },
    },
    "finals": {
        "name": "Finals",
        "active_periods": [1, 2, 3, 4, 5, 6],
        "periods": {
            "1": {"start": "08:00", "end": "09:50"},
            "2": {"start": "10:00", "end": "11:50"},
            "3": {"start": "12:30", "end": "14:20"},
            "4": {"start": "08:00", "end": "09:50"},
            "5": {"start": "10:00", "end": "11:50"},
            "6": {"start": "12:30", "end": "14:20"},
        },
    },
    "no_school": {
        "name": "No School",
        "active_periods": [],
        "periods": {},
    },
}

DEFAULT_CONFIG = {
    "schedules": DEFAULT_SCHEDULES,
    # Which schedule preset runs on each weekday
    "week_schedule": {
        "monday":    "regular_block_a",
        "tuesday":   "regular_block_b",
        "wednesday": "regular_block_a",
        "thursday":  "regular_block_b",
        "friday":    "regular_block_a",
        "saturday":  "no_school",
        "sunday":    "no_school",
    },
    # Date overrides: {"2026-04-01": "minimum_day_plc"}
    "date_overrides": {},
    # Students can scan this many minutes BEFORE the period starts and still be present
    "pre_scan_minutes": 7,
    # How long the OLED holds each message (seconds)
    "oled_message_duration": 6,
    # Feature toggles
    "attendance_enabled": True,
    "bathroom_enabled": True,
    # Semester definitions for analytics
    "semesters": {
        "fall_2025":   {"name": "Fall 2025",   "start": "2025-08-01", "end": "2025-12-31"},
        "spring_2026": {"name": "Spring 2026", "start": "2026-01-01", "end": "2026-05-31"},
    },
    "current_semester": "spring_2026",
}

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def load_config():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        stored = {}
        with open(CONFIG_FILE) as f:
            stored = json.load(f)
        # Merge in any new default keys so upgrades don't break existing installs
        merged = dict(DEFAULT_CONFIG)
        merged.update(stored)
        # Make sure all default schedules exist (add new ones without wiping custom edits)
        if "schedules" not in merged:
            merged["schedules"] = DEFAULT_SCHEDULES
        else:
            for key, val in DEFAULT_SCHEDULES.items():
                merged["schedules"].setdefault(key, val)
        return merged
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(config):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_schedule_for_date(config, date_str):
    """Return the schedule preset dict for a given date string (YYYY-MM-DD)."""
    # Date-specific override takes priority
    if date_str in config.get("date_overrides", {}):
        key = config["date_overrides"][date_str]
    else:
        from datetime import date as date_cls
        d = date_cls.fromisoformat(date_str)
        day_name = WEEKDAY_NAMES[d.weekday()]
        key = config.get("week_schedule", {}).get(day_name, "no_school")

    return config.get("schedules", {}).get(key, DEFAULT_SCHEDULES["no_school"]), key


def get_semester_for_date(config, date_str):
    """Return the semester key and dict for a given date string."""
    for key, sem in config.get("semesters", {}).items():
        if sem["start"] <= date_str <= sem["end"]:
            return key, sem
    return None, None
