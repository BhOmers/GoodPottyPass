import threading
import time as time_module
from datetime import datetime
from config import load_config

_lock = threading.Lock()
_current_period = None  # None means between periods / no class


def _time_to_minutes(t_str):
    h, m = map(int, t_str.split(":"))
    return h * 60 + m


def get_current_period_from_time(config=None):
    """Calculate which period is active right now based on config."""
    if config is None:
        config = load_config()
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    for p_str, times in config["periods"].items():
        start = _time_to_minutes(times["start"])
        end = _time_to_minutes(times["end"])
        if start <= now_min <= end:
            return int(p_str)
    return None


def get_current_period():
    with _lock:
        return _current_period


def set_current_period(period):
    global _current_period
    with _lock:
        _current_period = period


def period_watcher(stop_event):
    """
    Background daemon thread.
    Recalculates the active period every 30 seconds from the system clock.
    A manual override via set_current_period() will be overwritten on the
    next tick - that is intentional for auto-recovery. The teacher can also
    lock a period via the settings page which sets a flag below.
    """
    global _current_period, _manual_override
    while not stop_event.is_set():
        if not _manual_override:
            new_period = get_current_period_from_time()
            with _lock:
                _current_period = new_period
        time_module.sleep(30)


_manual_override = False


def enable_manual_override(period):
    global _manual_override
    _manual_override = True
    set_current_period(period)


def disable_manual_override():
    global _manual_override
    _manual_override = False
    new_period = get_current_period_from_time()
    set_current_period(new_period)


def is_manual_override():
    return _manual_override
