import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
DB_FILE = os.path.join(DATA_DIR, "attendance.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

DEFAULT_CONFIG = {
    "periods": {
        "0": {"start": "07:00", "end": "07:50", "name": "Period 0"},
        "1": {"start": "08:00", "end": "08:50", "name": "Period 1"},
        "2": {"start": "09:00", "end": "09:50", "name": "Period 2"},
        "3": {"start": "10:00", "end": "10:50", "name": "Period 3"},
        "4": {"start": "11:00", "end": "11:50", "name": "Period 4"},
        "5": {"start": "12:00", "end": "12:50", "name": "Period 5"},
        "6": {"start": "13:00", "end": "13:50", "name": "Period 6"},
        "7": {"start": "14:00", "end": "14:50", "name": "Period 7"},
    },
    "tardy_minutes": 5,
    "oled_message_duration": 4,
}


def load_config():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(config):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
