"""
scanner.py
Handles all RFID scan events.

Attendance logic:
  - Students can scan up to pre_scan_minutes BEFORE the period starts -> Present
  - At exactly the period start time or after -> Tardy
  - After the period ends -> ignored (no active period)

Bathroom logic:
  - 1st scan in period: attendance (see above)
  - Subsequent scans: bathroom pass system
"""

import threading
from datetime import datetime, date
import database as db
from config import load_config, get_schedule_for_date

# ── Registration State ────────────────────────────────────────────────────────

_reg_lock = threading.Lock()
_reg_mode = False
_reg_card_number = None


def start_registration(card_number):
    global _reg_mode, _reg_card_number
    with _reg_lock:
        _reg_mode = True
        _reg_card_number = card_number


def cancel_registration():
    global _reg_mode, _reg_card_number
    with _reg_lock:
        _reg_mode = False
        _reg_card_number = None


def is_registration_mode():
    with _reg_lock:
        return _reg_mode


def get_registration_card():
    with _reg_lock:
        return _reg_card_number


def handle_registration_scan(uid):
    global _reg_mode, _reg_card_number
    with _reg_lock:
        if not _reg_mode:
            return None
        card_num = _reg_card_number
        _reg_mode = False
        _reg_card_number = None

    if card_num is not None:
        db.register_card(uid, card_num)
        print(f"[REG] Card #{card_num} registered with UID {uid}")
        return card_num
    return None


# ── Tardy Logic ───────────────────────────────────────────────────────────────

def _determine_status(period, config):
    """
    Present  = scan arrives before the period's official start time
               (even during the pre_scan window)
    Tardy    = scan arrives at or after the official start time
    """
    now = datetime.now()
    now_min = now.hour * 60 + now.minute

    date_str = date.today().isoformat()
    schedule, _ = get_schedule_for_date(config, date_str)
    period_times = schedule.get("periods", {})
    p_str = str(period)

    if p_str in period_times:
        h, m = map(int, period_times[p_str]["start"].split(":"))
        start_min = h * 60 + m
        if now_min < start_min:
            return "present"   # scanning before the bell
        return "tardy"         # at or after the bell
    return "present"


# ── Main Scan Handler ─────────────────────────────────────────────────────────

def _today():
    return date.today().isoformat()


def handle_scan(uid, config, current_period):
    """
    Process a student card scan.
    Returns (line1, line2, line3) for the OLED display, or None to ignore.
    """
    today = _today()
    scan_time = datetime.now().strftime("%H:%M:%S")

    attendance_on = config.get("attendance_enabled", True)
    bathroom_on   = config.get("bathroom_enabled", True)

    if current_period is None:
        return ("No active period", "Not class time", "")

    card_number = db.get_card_number(uid)
    if card_number is None:
        return ("Unknown card!", f"UID ...{uid[-6:]}", "Register in dashboard")

    student = db.get_student(card_number, current_period)
    if student is None:
        return (f"Card #{card_number}", f"Not in P{current_period}", "")

    sid  = student["id"]
    name = student["name"]
    first = name.split()[0]

    # ── Attendance scan ───────────────────────────────────────────────────────
    att = db.get_student_attendance_status(sid, today, current_period)

    if att is None:
        if not attendance_on:
            # Attendance disabled: just acknowledge and allow bathroom use
            db.mark_attendance(sid, today, current_period, "present", scan_time)
            return (f"Hi {first}!", "Attendance off", "")

        status = _determine_status(current_period, config)
        db.mark_attendance(sid, today, current_period, status, scan_time)
        if status == "tardy":
            return ("TARDY", name, scan_time)
        return ("PRESENT", name, scan_time)

    # ── Bathroom scans ────────────────────────────────────────────────────────
    if not bathroom_on:
        return ("Bathroom pass", "is disabled", "")

    bathroom_out = db.get_current_bathroom_out(today, current_period)

    # Student is returning from bathroom
    if bathroom_out and bathroom_out["student_id"] == sid:
        out_dt = datetime.fromisoformat(bathroom_out["out_time"])
        mins   = (datetime.now() - out_dt).total_seconds() / 60.0
        db.end_bathroom_session(sid, today, current_period,
                                datetime.now().isoformat(), round(mins, 2))
        queue = db.get_bathroom_queue(today, current_period)
        if queue:
            next_name = queue[0]["name"].split()[0]
            return (f"Back: {first} ({mins:.0f}m)", f"NEXT: {next_name}!", "Scan to go")
        return (f"Welcome back!", f"{first}: {mins:.0f} min out", "")

    # Student is in the queue
    queue = db.get_bathroom_queue(today, current_period)
    in_queue = next((i for i, q in enumerate(queue) if q["student_id"] == sid), -1)

    if in_queue >= 0:
        if not bathroom_out:
            # Bathroom just freed up - let them go
            db.remove_from_bathroom_queue(sid, today, current_period)
            db.start_bathroom_session(sid, today, current_period,
                                      datetime.now().isoformat())
            return (f"Bathroom: {first}", "Scan when back", "")
        else:
            # Still occupied - cancel their spot
            db.remove_from_bathroom_queue(sid, today, current_period)
            return ("Removed from queue", first, "Scan again to rejoin")

    # Bathroom is occupied - add to queue
    if bathroom_out:
        db.add_to_bathroom_queue(sid, today, current_period,
                                 datetime.now().isoformat())
        queue = db.get_bathroom_queue(today, current_period)
        pos       = len(queue)
        out_first = bathroom_out["name"].split()[0]
        return (f"Queue #{pos}: {first}", f"Waiting for {out_first}", "Scan to cancel")

    # Bathroom is free - go!
    db.start_bathroom_session(sid, today, current_period,
                              datetime.now().isoformat())
    return (f"Bathroom: {first}", "Scan when back", "")
