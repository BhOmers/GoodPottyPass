import threading
import time as time_module
from datetime import datetime, date
from config import load_config, get_schedule_for_date

_lock = threading.Lock()
_current_period = None
_manual_override = False


def _time_to_minutes(t_str):
    h, m = map(int, t_str.split(":"))
    return h * 60 + m


def get_todays_schedule(config=None, date_str=None):
    """Return (schedule_dict, schedule_key) for today or a given date."""
    if config is None:
        config = load_config()
    if date_str is None:
        date_str = date.today().isoformat()
    return get_schedule_for_date(config, date_str)


def get_current_period_from_time(config=None, date_str=None):
    """Return the period number active right now, or None."""
    if config is None:
        config = load_config()
    if date_str is None:
        date_str = date.today().isoformat()

    schedule, _ = get_todays_schedule(config, date_str)
    active_periods = schedule.get("active_periods", [])
    period_times = schedule.get("periods", {})

    now = datetime.now()
    now_min = now.hour * 60 + now.minute

    for p in active_periods:
        p_str = str(p)
        if p_str not in period_times:
            continue
        start = _time_to_minutes(period_times[p_str]["start"])
        end = _time_to_minutes(period_times[p_str]["end"])
        # Include pre_scan window so the period "opens" early for scanning
        pre_scan = int(config.get("pre_scan_minutes", 7))
        if (start - pre_scan) <= now_min <= end:
            return int(p)
    return None


def get_active_periods_today(config=None, date_str=None):
    """Return the list of active period numbers for today."""
    if config is None:
        config = load_config()
    if date_str is None:
        date_str = date.today().isoformat()
    schedule, _ = get_todays_schedule(config, date_str)
    return schedule.get("active_periods", [])


def get_current_period():
    with _lock:
        return _current_period


def set_current_period(period):
    global _current_period
    with _lock:
        _current_period = period


def enable_manual_override(period):
    global _manual_override
    _manual_override = True
    set_current_period(period)


def disable_manual_override():
    global _manual_override
    _manual_override = False
    set_current_period(get_current_period_from_time())


def is_manual_override():
    return _manual_override


def period_watcher(stop_event):
    """Background thread: recalculates active period every 20 seconds."""
    global _current_period
    while not stop_event.is_set():
        if not _manual_override:
            new_period = get_current_period_from_time()
            with _lock:
                _current_period = new_period
        time_module.sleep(20)
