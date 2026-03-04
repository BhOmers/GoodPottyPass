import os
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify)
import database as db
import scanner as sc
from period_manager import (get_current_period, set_current_period,
                             get_current_period_from_time,
                             enable_manual_override, disable_manual_override,
                             is_manual_override)
from config import load_config, save_config, UPLOAD_DIR

app = Flask(__name__)
app.secret_key = os.urandom(24)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def today():
    return date.today().isoformat()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    period = get_current_period()
    config = load_config()
    att, counts, bathroom_out, queue = [], {}, None, []

    if period is not None:
        att = db.get_attendance(today(), period)
        counts = {"present": 0, "tardy": 0, "absent": 0, "total": len(att)}
        for s in att:
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        bathroom_out = db.get_current_bathroom_out(today(), period)
        queue = db.get_bathroom_queue(today(), period)
        # Annotate bathroom_out with elapsed minutes
        if bathroom_out:
            out_dt = datetime.fromisoformat(bathroom_out["out_time"])
            bathroom_out = dict(bathroom_out)
            bathroom_out["minutes_out"] = round(
                (datetime.now() - out_dt).total_seconds() / 60, 1
            )

    p_cfg = config["periods"].get(str(period), {}) if period is not None else {}

    return render_template(
        "dashboard.html",
        period=period,
        period_cfg=p_cfg,
        students=att,
        counts=counts,
        bathroom_out=bathroom_out,
        queue=queue,
        now=datetime.now().strftime("%I:%M %p"),
        today=today(),
        manual_override=is_manual_override(),
        all_periods=sorted(config["periods"].keys(), key=int),
    )


# ── Attendance ────────────────────────────────────────────────────────────────

@app.route("/attendance")
def attendance():
    config = load_config()
    period = int(request.args.get("period", get_current_period() or 1))
    att = db.get_attendance(today(), period)
    all_periods = sorted(config["periods"].keys(), key=int)
    return render_template("attendance.html",
                           attendance=att, period=period,
                           all_periods=all_periods, today=today())


@app.route("/attendance/update", methods=["POST"])
def update_attendance():
    sid = int(request.form["student_id"])
    new_status = request.form["status"]
    period = int(request.form["period"])
    db.manual_status_change(sid, today(), period, new_status)
    flash(f"Status updated to {new_status.upper()}", "success")
    return redirect(url_for("attendance", period=period))


# ── Bathroom ──────────────────────────────────────────────────────────────────

@app.route("/bathroom")
def bathroom():
    period = int(request.args.get("period", get_current_period() or 1))
    config = load_config()
    bathroom_out = db.get_current_bathroom_out(today(), period)
    if bathroom_out:
        out_dt = datetime.fromisoformat(bathroom_out["out_time"])
        bathroom_out = dict(bathroom_out)
        bathroom_out["minutes_out"] = round(
            (datetime.now() - out_dt).total_seconds() / 60, 1
        )
    queue = db.get_bathroom_queue(today(), period)
    log = db.get_bathroom_log(today(), period)
    students = db.get_all_students(period)
    students_with_totals = [
        {**s, "total_minutes": db.get_bathroom_total_minutes(s["id"])}
        for s in students
    ]
    # Sort by most time spent, descending
    students_with_totals.sort(key=lambda s: s["total_minutes"], reverse=True)
    all_periods = sorted(config["periods"].keys(), key=int)

    return render_template("bathroom.html",
                           bathroom_out=bathroom_out, queue=queue,
                           log=log, period=period,
                           students_with_totals=students_with_totals,
                           all_periods=all_periods, now=datetime.now().strftime("%I:%M %p"))


@app.route("/bathroom/force_return", methods=["POST"])
def force_return():
    sid = int(request.form["student_id"])
    period = int(request.form["period"])
    in_time = datetime.now().isoformat()
    # Find out_time to compute duration
    out_info = db.get_current_bathroom_out(today(), period)
    if out_info and out_info["student_id"] == sid:
        out_dt = datetime.fromisoformat(out_info["out_time"])
        mins = round((datetime.now() - out_dt).total_seconds() / 60, 2)
        db.force_return_bathroom(sid, today(), period, in_time, mins)
        flash("Student marked as returned.", "success")
    else:
        flash("Student is not currently out.", "error")
    return redirect(url_for("bathroom", period=period))


@app.route("/bathroom/remove_queue", methods=["POST"])
def remove_queue():
    sid = int(request.form["student_id"])
    period = int(request.form["period"])
    db.remove_from_bathroom_queue(sid, today(), period)
    flash("Removed from queue.", "success")
    return redirect(url_for("bathroom", period=period))


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
def settings():
    config = load_config()
    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_periods":
            for p in range(8):
                ps = str(p)
                start = request.form.get(f"p{p}_start")
                end = request.form.get(f"p{p}_end")
                name = request.form.get(f"p{p}_name")
                if start and end:
                    config["periods"][ps] = {
                        "start": start, "end": end,
                        "name": name or f"Period {p}"
                    }
            config["tardy_minutes"] = int(request.form.get("tardy_minutes", 5))
            save_config(config)
            flash("Settings saved.", "success")

        elif action == "manual_period":
            val = request.form.get("manual_period_val")
            if val == "auto":
                disable_manual_override()
                flash("Switched to automatic period detection.", "success")
            else:
                enable_manual_override(int(val))
                flash(f"Manually set to Period {val}.", "success")

        return redirect(url_for("settings"))

    return render_template("settings.html",
                           config=config,
                           current_period=get_current_period(),
                           manual_override=is_manual_override(),
                           all_periods=list(range(8)))


# ── Roster Upload ─────────────────────────────────────────────────────────────

@app.route("/upload", methods=["GET", "POST"])
def upload_roster():
    if request.method == "POST":
        f = request.files.get("roster_file")
        if not f or not f.filename.endswith(".xml"):
            flash("Please upload a valid .xml file.", "error")
            return redirect(url_for("upload_roster"))

        path = os.path.join(UPLOAD_DIR, f.filename)
        f.save(path)

        try:
            tree = ET.parse(path)
            root = tree.getroot()
            replace = request.form.get("replace") == "yes"
            imported = 0

            for period_el in root.findall("period"):
                period_num = int(period_el.get("number"))
                if replace:
                    db.clear_roster(period_num)
                for s_el in period_el.findall("student"):
                    card = int(s_el.get("card_number"))
                    name = (s_el.text or "").strip()
                    if name:
                        db.add_student(card, name, period_num)
                        imported += 1

            flash(f"Imported {imported} students successfully!", "success")
        except Exception as e:
            flash(f"XML parse error: {e}", "error")

        return redirect(url_for("upload_roster"))

    students = db.get_all_students()
    by_period = {}
    for s in students:
        by_period.setdefault(s["period"], []).append(s)

    return render_template("upload.html", by_period=by_period)


# ── Card Registration ─────────────────────────────────────────────────────────

@app.route("/register")
def register_cards():
    regs = db.get_all_card_registrations()
    registered = {r["card_number"] for r in regs}
    return render_template("register.html",
                           registrations=regs,
                           registered=registered,
                           is_registering=sc.is_registration_mode(),
                           pending_card=sc.get_registration_card(),
                           all_cards=range(1, 51))


@app.route("/register/start/<int:card_number>")
def start_registration(card_number):
    sc.start_registration(card_number)
    flash(f"Tap the physical RFID card you want to assign to Card #{card_number}.", "info")
    return redirect(url_for("register_cards"))


@app.route("/register/cancel")
def cancel_registration():
    sc.cancel_registration()
    flash("Registration cancelled.", "warning")
    return redirect(url_for("register_cards"))


@app.route("/register/delete/<int:card_number>")
def delete_registration(card_number):
    db.delete_card_registration(card_number)
    flash(f"Card #{card_number} unregistered.", "success")
    return redirect(url_for("register_cards"))


# ── Live Status API (AJAX) ────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    period = get_current_period()
    counts = {"present": 0, "tardy": 0, "absent": 0, "total": 0}
    bathroom_out = None
    queue = []

    if period is not None:
        att = db.get_attendance(today(), period)
        counts["total"] = len(att)
        for s in att:
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        bo = db.get_current_bathroom_out(today(), period)
        if bo:
            out_dt = datetime.fromisoformat(bo["out_time"])
            mins = round((datetime.now() - out_dt).total_seconds() / 60, 1)
            bathroom_out = {"name": bo["name"], "minutes": mins}
        queue = [{"name": q["name"]} for q in db.get_bathroom_queue(today(), period)]

    return jsonify({
        "period": period,
        "time": datetime.now().strftime("%I:%M %p"),
        "counts": counts,
        "bathroom_out": bathroom_out,
        "queue": queue,
        "registration_mode": sc.is_registration_mode(),
        "registration_card": sc.get_registration_card(),
        "manual_override": is_manual_override(),
    })
