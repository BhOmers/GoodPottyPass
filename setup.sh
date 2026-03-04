#!/bin/bash
# setup.sh - First-time setup for the Attendance System on Raspberry Pi 3 B+
# Run with: bash setup.sh

set -e

echo "============================================"
echo "  Attendance System - Pi Setup"
echo "============================================"

# Enable SPI (for MFRC522) and I2C (for OLED)
echo "[1/5] Enabling SPI and I2C interfaces..."
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
echo "  SPI and I2C enabled."

# Update and install system packages
echo "[2/5] Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
  python3-pip \
  python3-pil \
  i2c-tools \
  fonts-dejavu-core \
  libfreetype6-dev \
  libjpeg-dev \
  zlib1g-dev

# Install Python packages
echo "[3/5] Installing Python dependencies..."
pip3 install --break-system-packages flask mfrc522 RPi.GPIO spidev luma.oled luma.core Pillow 2>/dev/null || \
pip3 install flask mfrc522 RPi.GPIO spidev luma.oled luma.core Pillow

# Create data directories
echo "[4/5] Creating data directories..."
mkdir -p data uploads
chmod 755 data uploads

# Create systemd service for autostart
echo "[5/5] Creating systemd service..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo tee /etc/systemd/system/attendance.service > /dev/null <<EOF
[Unit]
Description=Attendance & Bathroom Pass System
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable attendance.service

echo ""
echo "============================================"
echo "  Setup complete!"
echo ""
echo "  To start now:    sudo systemctl start attendance"
echo "  To stop:         sudo systemctl stop attendance"
echo "  To view logs:    journalctl -u attendance -f"
echo "  Or run directly: python3 main.py"
echo ""
echo "  Dashboard: http://$(hostname -I | awk '{print $1}'):5000"
echo "============================================"
