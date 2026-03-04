"""
scanner.py
Handles all RFID scan events.

Scan flow per student:
  1st scan in a period  -> mark attendance (present or tardy)
  2nd scan onward       -> bathroom pass system
"""

import threading
from datetime import datetime, date
import database as db

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
    """
    Called when a card is tapped during registration mode.
    Stores uid -> card_number in the DB and clears registration state.
    Returns the card_number that was registered, or None.
    """
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


# ── Attendance / Bathroom Logic ───────────────────────────────────────────────

def _today():
    return date.today().isoformat()


def _determine_status(period, config):
    """Returns 'present' or 'tardy' based on the current time vs period start."""
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    p_str = str(period)
    if p_str in config.get("periods", {}):
        h, m = map(int, config["periods"][p_str]["start"].split(":"))
        start_min = h * 60 + m
        if now_min <= start_min + int(config.get("tardy_minutes", 5)):
            return "present"
        return "tardy"
    return "present"


def handle_scan(uid, config, current_period):
    """
    Process a student scan. Returns (line1, line2, line3) tuple for the OLED,
    or None if the scan should be silently ignored.
    """
    today = _today()
    scan_time = datetime.now().strftime("%H:%M:%S")

    if current_period is None:
        return ("No active period", "Not class time", "")

    # Look up UID -> card number
    card_number = db.get_card_number(uid)
    if card_number is None:
        return ("Unknown card!", f"UID ...{uid[-6:]}", "Register in dashboard")

    # Look up student in current period
    student = db.get_student(card_number, current_period)
    if student is None:
        return (f"Card #{card_number}", f"Not in Period {current_period}", "")

    sid = student["id"]
    name = student["name"]
    first = name.split()[0]

    # ── First scan of the period: attendance ──────────────────────────────────
    att = db.get_student_attendance_status(sid, today, current_period)
    if att is None:
        status = _determine_status(current_period, config)
        db.mark_attendance(sid, today, current_period, status, scan_time)
        if status == "tardy":
            return ("TARDY", name, scan_time)
        return ("PRESENT", name, scan_time)

    # ── Subsequent scans: bathroom pass ───────────────────────────────────────
    bathroom_out = db.get_current_bathroom_out(today, current_period)

    # Student is returning from bathroom
    if bathroom_out and bathroom_out["student_id"] == sid:
        out_dt = datetime.fromisoformat(bathroom_out["out_time"])
        mins = (datetime.now() - out_dt).total_seconds() / 60.0
        db.end_bathroom_session(sid, today, current_period,
                                datetime.now().isoformat(), round(mins, 2))
        queue = db.get_bathroom_queue(today, current_period)
        if queue:
            next_name = queue[0]["name"].split()[0]
            return (f"Back: {first} ({mins:.0f}m)", f"NEXT UP: {next_name}!", "Scan to go")
        return (f"Welcome back!", f"{first}: {mins:.0f} min out", "")

    # Student is in the queue and scanning again -> cancel their spot
    queue = db.get_bathroom_queue(today, current_period)
    in_queue = next((i for i, q in enumerate(queue) if q["student_id"] == sid), -1)
    if in_queue >= 0:
        db.remove_from_bathroom_queue(sid, today, current_period)
        return (f"Removed from queue", first, "Scan again to rejoin")

    # Someone is already out -> add to queue
    if bathroom_out:
        db.add_to_bathroom_queue(sid, today, current_period, datetime.now().isoformat())
        queue = db.get_bathroom_queue(today, current_period)  # refresh for count
        pos = len(queue)
        out_first = bathroom_out["name"].split()[0]
        return (f"Queue #{pos} for {first}", f"Waiting for {out_first}", "Scan to cancel")

    # Bathroom is free -> go!
    db.start_bathroom_session(sid, today, current_period, datetime.now().isoformat())
    return (f"Bathroom: {first}", "Scan when back", "")
