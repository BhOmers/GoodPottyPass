"""
main.py  -  Attendance & Bathroom Pass System
Run with:  python3 main.py

The teacher accesses the dashboard at:  http://<pi-ip>:5000
Find the Pi's IP on the OLED at startup, or run: hostname -I
"""

import threading
import signal
import sys
import time
import socket
from datetime import datetime, date

import database as db
from config import load_config
from rfid_handler import RFIDReader
from oled_handler import OLEDDisplay
from period_manager import (get_current_period, set_current_period,
                             get_current_period_from_time, period_watcher)
import scanner as sc
from web_app import app


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def today():
    return date.today().isoformat()


# ── RFID Loop ─────────────────────────────────────────────────────────────────

def rfid_loop(reader: RFIDReader, oled: OLEDDisplay, stop_event: threading.Event):
    """
    Continuously polls the RFID reader.
    - Debounces repeated scans (same UID within 2 seconds).
    - Routes to registration handler or normal scan handler.
    - Updates the OLED idle screen when idle.
    """
    last_uid = None
    last_scan_time = 0.0
    message_expires = 0.0
    DEBOUNCE = 2.0
    MESSAGE_HOLD = 0.0  # set per scan from config

    while not stop_event.is_set():
        uid = reader.read_no_block()
        now = time.monotonic()
        config = load_config()
        MESSAGE_HOLD = float(config.get("oled_message_duration", 4))

        if uid and (uid != last_uid or (now - last_scan_time) > DEBOUNCE):
            last_uid = uid
            last_scan_time = now
            message_expires = now + MESSAGE_HOLD

            if sc.is_registration_mode():
                card_num = sc.handle_registration_scan(uid)
                if card_num:
                    oled.show_message(f"Registered!", f"Card #{card_num}", str(uid[-8:]))
                else:
                    oled.show_message("Registration", "cancelled", "")
            else:
                result = sc.handle_scan(uid, config, get_current_period())
                if result:
                    oled.show_message(*result)

        # Idle display when no active message
        elif now > message_expires:
            period = get_current_period()
            time_str = datetime.now().strftime("%I:%M %p")
            if period is not None:
                att = db.get_attendance(today(), period)
                present = sum(1 for a in att if a["status"] in ("present", "tardy"))
                total = len(att)
            else:
                present, total = 0, 0
            oled.show_idle(period, time_str, present, total)

        time.sleep(0.15)


# ── Flask thread ──────────────────────────────────────────────────────────────

def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  Attendance & Bathroom Pass System")
    print("=" * 50)

    # Init DB
    db.init_db()
    print("[DB] Initialized.")

    # Init hardware
    reader = RFIDReader()
    oled = OLEDDisplay()

    # Show startup screen with IP
    ip = get_local_ip()
    oled.show_startup(ip)
    print(f"[NET] Dashboard: http://{ip}:5000")

    # Set initial period
    config = load_config()
    initial_period = get_current_period_from_time(config)
    set_current_period(initial_period)
    print(f"[PERIOD] Starting period: {initial_period}")

    stop_event = threading.Event()

    # Period watcher thread
    period_thread = threading.Thread(
        target=period_watcher, args=(stop_event,), daemon=True, name="PeriodWatcher"
    )
    period_thread.start()

    # RFID loop thread
    rfid_thread = threading.Thread(
        target=rfid_loop, args=(reader, oled, stop_event), daemon=True, name="RFIDLoop"
    )
    rfid_thread.start()

    # Flask in its own thread
    flask_thread = threading.Thread(
        target=run_flask, daemon=True, name="Flask"
    )
    flask_thread.start()

    # Graceful shutdown
    def shutdown(sig, frame):
        print("\n[SHUTDOWN] Stopping...")
        stop_event.set()
        reader.cleanup()
        oled.clear()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("[OK] System running. Press Ctrl+C to stop.\n")

    # Keep main thread alive
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
