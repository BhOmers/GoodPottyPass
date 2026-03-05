import os
import csv
import io
import xml.etree.ElementTree as ET
from datetime import datetime, date
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, Response)
import database as db
import scanner as sc
from period_manager import (get_current_period, set_current_period,
                             get_current_period_from_time,
                             enable_manual_override, disable_manual_override,
                             is_manual_override, get_todays_schedule,
                             get_active_periods_today)
from config import (load_config, save_config, UPLOAD_DIR,
                    WEEKDAY_NAMES, get_schedule_for_date, get_semester_for_date)

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), "templates"),
            static_folder=os.path.join(os.path.dirname(__file__), "static"))
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
    schedule, schedule_key = get_todays_schedule(config)

    if period is not None:
        att = db.get_attendance(today(), period)
        counts = {"present": 0, "tardy": 0, "absent": 0, "total": len(att)}
        for s in att:
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        bathroom_out = db.get_current_bathroom_out(today(), period)
        queue = db.get_bathroom_queue(today(), period)
        if bathroom_out:
            out_dt = datetime.fromisoformat(bathroom_out["out_time"])
            bathroom_out = dict(bathroom_out)
            bathroom_out["minutes_out"] = round(
                (datetime.now() - out_dt).total_seconds() / 60, 1
            )

    active_periods = get_active_periods_today(config)

    return render_template(
        "dashboard.html",
        period=period,
        schedule=schedule,
        schedule_key=schedule_key,
        students=att,
        counts=counts,
        bathroom_out=bathroom_out,
        queue=queue,
        now=datetime.now().strftime("%I:%M %p"),
        today=today(),
        manual_override=is_manual_override(),
        active_periods=active_periods,
        config=config,
    )


# ── Attendance ────────────────────────────────────────────────────────────────

@app.route("/attendance")
def attendance():
    config = load_config()
    active = get_active_periods_today(config)
    default_period = get_current_period() or (active[0] if active else 1)
    period = int(request.args.get("period", default_period))
    att = db.get_attendance(today(), period)
    return render_template("attendance.html",
                           attendance=att, period=period,
                           active_periods=active, today=today(),
                           config=config)


@app.route("/attendance/update", methods=["POST"])
def update_attendance():
    sid = int(request.form["student_id"])
    new_status = request.form["status"]
    period = int(request.form["period"])
    db.manual_status_change(sid, today(), period, new_status)
    flash(f"Status updated to {new_status.upper()}.", "success")
    return redirect(url_for("attendance", period=period))


# ── Bathroom ──────────────────────────────────────────────────────────────────

@app.route("/bathroom")
def bathroom():
    config = load_config()
    active = get_active_periods_today(config)
    default_period = get_current_period() or (active[0] if active else 1)
    period = int(request.args.get("period", default_period))

    bathroom_out = db.get_current_bathroom_out(today(), period)
    if bathroom_out:
        out_dt = datetime.fromisoformat(bathroom_out["out_time"])
        bathroom_out = dict(bathroom_out)
        bathroom_out["minutes_out"] = round(
            (datetime.now() - out_dt).total_seconds() / 60, 1
        )

    queue   = db.get_bathroom_queue(today(), period)
    log     = db.get_bathroom_log(today(), period)
    sem_key = config.get("current_semester")
    sem     = config.get("semesters", {}).get(sem_key, {})
    start_d = sem.get("start", "2000-01-01")
    end_d   = sem.get("end",   "2099-12-31")

    students = db.get_all_students(period)
    students_with_totals = [
        {**s, **db.get_bathroom_total_minutes(s["id"], start_d, end_d)}
        for s in students
    ]
    students_with_totals.sort(key=lambda s: s["total_minutes"], reverse=True)

    return render_template("bathroom.html",
                           bathroom_out=bathroom_out, queue=queue,
                           log=log, period=period,
                           students_with_totals=students_with_totals,
                           active_periods=active,
                           sem_name=sem.get("name", "This Semester"),
                           now=datetime.now().strftime("%I:%M %p"),
                           config=config)


@app.route("/bathroom/force_return", methods=["POST"])
def force_return():
    sid    = int(request.form["student_id"])
    period = int(request.form["period"])
    out_info = db.get_current_bathroom_out(today(), period)
    if out_info and out_info["student_id"] == sid:
        out_dt = datetime.fromisoformat(out_info["out_time"])
        mins   = round((datetime.now() - out_dt).total_seconds() / 60, 2)
        db.force_return_bathroom(sid, today(), period, datetime.now().isoformat(), mins)
        flash("Student marked as returned.", "success")
    else:
        flash("Student is not currently out.", "error")
    return redirect(url_for("bathroom", period=period))


@app.route("/bathroom/remove_queue", methods=["POST"])
def remove_queue():
    sid    = int(request.form["student_id"])
    period = int(request.form["period"])
    db.remove_from_bathroom_queue(sid, today(), period)
    flash("Removed from queue.", "success")
    return redirect(url_for("bathroom", period=period))


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.route("/analytics")
def analytics():
    config  = load_config()
    sem_key = request.args.get("semester", config.get("current_semester", ""))
    sem     = config.get("semesters", {}).get(sem_key, {})
    start_d = request.args.get("start", sem.get("start", "2000-01-01"))
    end_d   = request.args.get("end",   sem.get("end",   today()))
    period  = request.args.get("period", None)
    if period:
        period = int(period)

    analytics_data = db.get_all_bathroom_analytics(period, start_d, end_d)
    daily_trend    = db.get_bathroom_daily_trend(start_d, end_d, period)
    active_periods = get_active_periods_today(config)

    # Student-level weekly trends for the top 5 bathroom users
    student_trends = {}
    for row in analytics_data[:5]:
        weeks = db.get_bathroom_weekly_trend(row["student_id"], start_d, end_d)
        student_trends[row["student_id"]] = {
            "name":  row["name"],
            "weeks": weeks,
        }

    return render_template("analytics.html",
                           analytics_data=analytics_data,
                           daily_trend=daily_trend,
                           student_trends=student_trends,
                           semesters=config.get("semesters", {}),
                           sem_key=sem_key,
                           start_d=start_d,
                           end_d=end_d,
                           period=period,
                           active_periods=active_periods,
                           config=config)


@app.route("/analytics/export")
def analytics_export():
    config  = load_config()
    sem_key = request.args.get("semester", config.get("current_semester", ""))
    sem     = config.get("semesters", {}).get(sem_key, {})
    start_d = request.args.get("start", sem.get("start", "2000-01-01"))
    end_d   = request.args.get("end",   today())
    period  = request.args.get("period", None)
    if period:
        period = int(period)

    data = db.get_all_bathroom_analytics(period, start_d, end_d)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Card #", "Name", "Period", "Total Minutes",
                     "Trips", "Avg Minutes Per Trip", "Date Range"])
    for row in data:
        writer.writerow([
            row["card_number"],
            row["name"],
            row["period"],
            row["total_minutes"],
            row["trips"],
            row["avg_minutes"],
            f"{start_d} to {end_d}",
        ])

    output.seek(0)
    filename = f"bathroom_analytics_{start_d}_to_{end_d}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Schedules ─────────────────────────────────────────────────────────────────

@app.route("/schedules", methods=["GET", "POST"])
def schedules():
    config = load_config()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_week":
            for day in WEEKDAY_NAMES:
                val = request.form.get(f"day_{day}")
                if val:
                    config["week_schedule"][day] = val
            save_config(config)
            flash("Weekly schedule saved.", "success")

        elif action == "save_preset":
            key  = request.form.get("preset_key", "").strip()
            name = request.form.get("preset_name", "").strip()
            if not key or not name:
                flash("Preset key and name are required.", "error")
                return redirect(url_for("schedules"))

            active_str = request.form.get("active_periods", "")
            try:
                active = [int(x.strip()) for x in active_str.split(",") if x.strip()]
            except ValueError:
                flash("Active periods must be comma-separated numbers.", "error")
                return redirect(url_for("schedules"))

            periods = {}
            for p in range(8):
                s = request.form.get(f"p{p}_start")
                e = request.form.get(f"p{p}_end")
                if s and e:
                    periods[str(p)] = {"start": s, "end": e}

            config["schedules"][key] = {
                "name": name,
                "active_periods": active,
                "periods": periods,
            }
            save_config(config)
            flash(f"Schedule '{name}' saved.", "success")

        elif action == "delete_preset":
            key = request.form.get("preset_key")
            protected = ["no_school"]
            if key in protected:
                flash("Cannot delete built-in schedules.", "error")
            elif key in config["schedules"]:
                del config["schedules"][key]
                # Clear any week assignments pointing to this key
                for day in WEEKDAY_NAMES:
                    if config["week_schedule"].get(day) == key:
                        config["week_schedule"][day] = "no_school"
                save_config(config)
                flash("Schedule deleted.", "success")

        elif action == "save_date_override":
            d   = request.form.get("override_date")
            key = request.form.get("override_schedule")
            if d and key:
                config.setdefault("date_overrides", {})[d] = key
                save_config(config)
                flash(f"Override set for {d}.", "success")

        elif action == "delete_date_override":
            d = request.form.get("override_date")
            config.get("date_overrides", {}).pop(d, None)
            save_config(config)
            flash("Override removed.", "success")

        return redirect(url_for("schedules"))

    overrides_sorted = sorted(config.get("date_overrides", {}).items())
    return render_template("schedules.html",
                           config=config,
                           weekday_names=WEEKDAY_NAMES,
                           overrides=overrides_sorted,
                           today=today())


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
def settings():
    config = load_config()
    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_general":
            config["pre_scan_minutes"]     = int(request.form.get("pre_scan_minutes", 7))
            config["oled_message_duration"] = int(request.form.get("oled_message_duration", 6))
            config["attendance_enabled"]    = "attendance_enabled" in request.form
            config["bathroom_enabled"]      = "bathroom_enabled" in request.form
            save_config(config)
            flash("General settings saved.", "success")

        elif action == "manual_period":
            val = request.form.get("manual_period_val")
            if val == "auto":
                disable_manual_override()
                flash("Switched to automatic period detection.", "success")
            else:
                enable_manual_override(int(val))
                flash(f"Manually set to Period {val}.", "success")

        elif action == "save_semesters":
            semesters = {}
            keys   = request.form.getlist("sem_key")
            names  = request.form.getlist("sem_name")
            starts = request.form.getlist("sem_start")
            ends   = request.form.getlist("sem_end")
            for k, n, s, e in zip(keys, names, starts, ends):
                if k and n and s and e:
                    semesters[k] = {"name": n, "start": s, "end": e}
            config["semesters"] = semesters
            config["current_semester"] = request.form.get("current_semester", "")
            save_config(config)
            flash("Semester settings saved.", "success")

        return redirect(url_for("settings"))

    active_periods = get_active_periods_today(config)
    return render_template("settings.html",
                           config=config,
                           current_period=get_current_period(),
                           manual_override=is_manual_override(),
                           active_periods=active_periods,
                           weekday_names=WEEKDAY_NAMES)


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
            replace  = request.form.get("replace") == "yes"
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

    students  = db.get_all_students()
    by_period = {}
    for s in students:
        by_period.setdefault(s["period"], []).append(s)

    return render_template("upload.html", by_period=by_period)


# ── Card Registration ─────────────────────────────────────────────────────────

@app.route("/register")
def register_cards():
    regs       = db.get_all_card_registrations()
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
    flash(f"Tap the physical card for Card #{card_number} on the reader.", "info")
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


# ── Live Status API ───────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    config = load_config()
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
            mins   = round((datetime.now() - out_dt).total_seconds() / 60, 1)
            bathroom_out = {"name": bo["name"], "minutes": mins}
        queue = [{"name": q["name"]} for q in db.get_bathroom_queue(today(), period)]

    schedule, schedule_key = get_todays_schedule(config)

    return jsonify({
        "period":            period,
        "time":              datetime.now().strftime("%I:%M %p"),
        "counts":            counts,
        "bathroom_out":      bathroom_out,
        "queue":             queue,
        "registration_mode": sc.is_registration_mode(),
        "registration_card": sc.get_registration_card(),
        "manual_override":   is_manual_override(),
        "schedule_name":     schedule.get("name", ""),
        "attendance_enabled": config.get("attendance_enabled", True),
        "bathroom_enabled":   config.get("bathroom_enabled", True),
    })
