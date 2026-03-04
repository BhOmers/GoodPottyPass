"""
RFID handler for MFRC522 over SPI.

Wiring (Pi 3 B+):
  MFRC522   Raspberry Pi
  SDA    -> GPIO 8  (CE0)
  SCK    -> GPIO 11
  MOSI   -> GPIO 10
  MISO   -> GPIO 9
  RST    -> GPIO 25
  GND    -> GND
  3.3V   -> 3.3V
"""

try:
    from mfrc522 import SimpleMFRC522
    import RPi.GPIO as GPIO
    HARDWARE_AVAILABLE = True
except (ImportError, RuntimeError):
    HARDWARE_AVAILABLE = False
    print("[RFID] Hardware not available - running in simulation mode.")


class RFIDReader:
    def __init__(self):
        if HARDWARE_AVAILABLE:
            self.reader = SimpleMFRC522()
        else:
            self.reader = None

    def read_no_block(self):
        """
        Non-blocking read. Returns UID string or None.
        The UID is returned as a plain string so it can be stored in the DB.
        """
        if not HARDWARE_AVAILABLE:
            return None
        try:
            uid, _ = self.reader.read_no_block()
            if uid:
                return str(uid)
        except Exception as e:
            print(f"[RFID] Read error: {e}")
        return None

    def cleanup(self):
        if HARDWARE_AVAILABLE:
            try:
                GPIO.cleanup()
            except Exception:
                pass
