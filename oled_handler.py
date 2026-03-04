"""
OLED handler for SSD1306 128x32 over I2C.

Wiring:
  OLED    Raspberry Pi
  SDA  -> GPIO 2 (I2C SDA)
  SCL  -> GPIO 3 (I2C SCL)
  GND  -> GND
  VCC  -> 3.3V
"""

import threading
from PIL import Image, ImageDraw, ImageFont

try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    OLED_AVAILABLE = True
except (ImportError, RuntimeError):
    OLED_AVAILABLE = False
    print("[OLED] Hardware not available - display output to console.")

# Display dimensions for the 38x12mm 0.91" OLED
WIDTH = 128
HEIGHT = 32

# Try to load a small TTF font; fall back to PIL default
def _load_font(size=8):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/piboto/Piboto-Regular.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


class OLEDDisplay:
    def __init__(self, i2c_address=0x3C):
        self._lock = threading.Lock()
        if OLED_AVAILABLE:
            serial = i2c(port=1, address=i2c_address)
            self.device = ssd1306(serial, width=WIDTH, height=HEIGHT)
        else:
            self.device = None

        self.font_sm = _load_font(8)
        self.font_md = _load_font(10)

    # ── Public API ────────────────────────────────────────────────────────────

    def show_idle(self, period, time_str, present_count, total_count):
        """Idle screen: period name, time, and attendance count."""
        with self._lock:
            img = Image.new("1", (WIDTH, HEIGHT), 0)
            draw = ImageDraw.Draw(img)

            period_text = f"Period {period}" if period is not None else "No Class"
            draw.text((0, 0), period_text, font=self.font_md, fill=255)
            draw.text((0, 13), time_str, font=self.font_sm, fill=255)
            draw.text((66, 13), f"{present_count}/{total_count} here", font=self.font_sm, fill=255)

            self._render(img, f"{period_text} | {time_str} | {present_count}/{total_count}")

    def show_message(self, line1, line2="", line3=""):
        """Three-line message screen (max ~18 chars per line at 128px width)."""
        with self._lock:
            img = Image.new("1", (WIDTH, HEIGHT), 0)
            draw = ImageDraw.Draw(img)

            draw.text((0, 0),  line1[:20], font=self.font_sm, fill=255)
            draw.text((0, 11), line2[:20], font=self.font_sm, fill=255)
            draw.text((0, 22), line3[:20], font=self.font_sm, fill=255)

            self._render(img, f"{line1} | {line2} | {line3}")

    def show_startup(self, ip_address):
        """Boot splash with IP address."""
        with self._lock:
            img = Image.new("1", (WIDTH, HEIGHT), 0)
            draw = ImageDraw.Draw(img)
            draw.text((0, 0),  "Attendance System", font=self.font_sm, fill=255)
            draw.text((0, 11), f"IP: {ip_address}", font=self.font_sm, fill=255)
            draw.text((0, 22), "Port: 5000", font=self.font_sm, fill=255)
            self._render(img, f"STARTUP | {ip_address}:5000")

    def clear(self):
        with self._lock:
            if self.device:
                self.device.clear()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _render(self, img, console_fallback=""):
        if self.device:
            self.device.display(img)
        else:
            print(f"[OLED] {console_fallback}")
