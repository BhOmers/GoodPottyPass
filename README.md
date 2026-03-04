# Attendance & Bathroom Pass System
### Raspberry Pi 3 B+ | MFRC522 | SSD1306 OLED

A classroom tool that handles RFID-based attendance and a digital bathroom pass with a live teacher dashboard.

---

## Hardware

| Component | Connection |
|---|---|
| MFRC522 RFID reader | SPI (see below) |
| SSD1306 128x32 OLED | I2C (SDA=GPIO2, SCL=GPIO3) |

**MFRC522 wiring:**
```
MFRC522   Raspberry Pi GPIO
SDA    -> Pin 24 (GPIO 8, CE0)
SCK    -> Pin 23 (GPIO 11)
MOSI   -> Pin 19 (GPIO 10)
MISO   -> Pin 21 (GPIO 9)
RST    -> Pin 22 (GPIO 25)
GND    -> Pin 6  (GND)
3.3V   -> Pin 1  (3.3V)
```

---

## First-Time Setup

```bash
git clone <this-repo> attendance_system
cd attendance_system
bash setup.sh
sudo systemctl start attendance
```

Then open a browser on any computer on the same Wi-Fi and go to:
```
http://<pi-ip-address>:5000
```

The Pi's IP address is shown on the OLED at startup.

---

## How to Use

### Step 1 - Upload your roster
Go to **Roster** in the dashboard and upload an XML file with your students. See `example_roster.xml` for the format. You can have different students for each period (0–7). Card numbers 1–50 are the physical card slots.

### Step 2 - Register physical cards
Go to **Cards** and click **Register** next to each card number. Then tap the physical RFID card on the reader. This links the chip's UID to the slot number.

### Step 3 - Set your period schedule
Go to **Settings** and enter your school's period start and end times. Set the tardy window (how many minutes after the start a student can still be marked Present instead of Tardy).

### Step 4 - Use it
- The period switches automatically based on the clock.
- Students tap their card once to sign in (marks Present or Tardy).
- After signing in, tapping again requests the bathroom pass.
- If the pass is in use, they're added to a queue. The OLED shows who they're waiting for.
- Tapping again while in the queue removes them from it.
- When the student returns, they tap to end their session. The OLED announces who's next.

---

## Teacher Dashboard

| Page | What you can do |
|---|---|
| **Dashboard** | Live overview: current period, attendance counts, bathroom status, queue |
| **Attendance** | View and manually override any student's status (Present/Tardy/Absent) |
| **Bathroom** | See who's out and for how long, today's full log, total minutes per student |
| **Cards** | Register RFID chips to card numbers 1–50 |
| **Roster** | Upload XML rosters, view current students per period |
| **Settings** | Edit period times, tardy window, and manually override the current period |

---

## Connection Method

The Pi runs a Flask web server on port 5000. The teacher connects via their browser on the same network (school Wi-Fi). No apps or special software needed. The dashboard auto-refreshes every 8 seconds.

For a more permanent setup, you can assign the Pi a static IP address on your router using its MAC address.

---

## XML Roster Format

```xml
<?xml version="1.0" encoding="UTF-8"?>
<roster>
  <period number="1">
    <student card_number="1">Jane Smith</student>
    <student card_number="2">John Doe</student>
  </period>
  <period number="2">
    <student card_number="1">Carlos Martinez</student>
  </period>
</roster>
```

- `period number` is 0–7
- `card_number` is 1–50
- The same card number in different periods is fine (each class gets their own seat mapping)

---

## Bathroom Pass Logic

```
Student scans card
  └── Not yet signed in?
        └── Mark Present (within tardy window) or Tardy
  └── Already signed in?
        └── Student is currently OUT in bathroom?
              └── End their session, show elapsed time, announce who's next
        └── Student is in the queue?
              └── Remove them from queue (they changed their mind)
        └── Pass is occupied?
              └── Add them to queue, show position and who they're waiting for
        └── Pass is free?
              └── Send them to bathroom, start timer
```

---

## Running as a Service

```bash
sudo systemctl start attendance    # start
sudo systemctl stop attendance     # stop
sudo systemctl restart attendance  # restart
journalctl -u attendance -f        # live logs
```

The service auto-starts on boot after running `setup.sh`.

---

## Project Structure

```
attendance_system/
├── main.py           # Entry point, threads for RFID + Flask + period watcher
├── config.py         # Period times, paths, defaults
├── database.py       # All SQLite queries
├── rfid_handler.py   # MFRC522 wrapper
├── oled_handler.py   # SSD1306 wrapper
├── period_manager.py # Auto period detection + manual override
├── scanner.py        # Attendance and bathroom scan logic
├── web_app.py        # Flask routes (teacher dashboard)
├── templates/        # Jinja2 HTML templates
├── static/           # CSS
├── data/             # SQLite database + config (auto-created)
├── uploads/          # Saved XML roster files
├── example_roster.xml
└── setup.sh
```
