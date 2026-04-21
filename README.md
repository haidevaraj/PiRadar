# 🛩️ PiRadar

> A real-time flight tracker for Raspberry Pi with voice alerts and OLED display

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![License: Source-Available](https://img.shields.io/badge/License-Source--Available-green.svg)](LICENSE.md)
[![Raspberry Pi 5](https://img.shields.io/badge/Raspberry%20Pi-5-red.svg)](https://www.raspberrypi.com)

---

## ✨ What is PiRadar?

PiRadar monitors aircraft in your airspace and alerts you in real-time with:
- 🔊 **Voice announcements** via Bluetooth speaker (Indian English or US English)
- 📱 **Live OLED display** showing flight details (callsign, route, altitude, speed)
- 🎵 **Smart audio alerts** (chime for normal flights, alert tone for emergency squawks)
- 🌐 **OpenSky Network API** for continuous flight tracking
- ✈️ **FlightAware enrichment** (optional) for airline names and routes
- 🗺️ **Airport database lookups** for origin/destination info

---

## 🚀 Quick Start

### Prerequisites
- **Raspberry Pi 5** (or Pi 4, Pi Zero 2W)
- **Python 3.11+**
- **Bluetooth speaker** (or HDMI audio)
- **Optional:** 2.42" SSD1309 OLED display (I2C)
- **WiFi connection**

### 1️⃣ Clone & Setup

```bash
git clone https://github.com/haidevaraj/PiRadar.git
cd PiRadar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2️⃣ Configure

```bash
cp config.example.toml config.toml
nano config.toml
```

Fill in:
- `latitude` & `longitude` (your location)
- `radius_miles` (detection range)
- OpenSky API credentials
- Bluetooth speaker volume
- Snooze hours (optional)

### 3️⃣ Run

```bash
python3 main.py
```

See flights detected on your OLED and hear voice alerts! 🎉

---

## 📋 Hardware Setup

### What You'll Need

| Component | Purpose | Link |
|-----------|---------|------|
| **Raspberry Pi 5 4GB** | Main processor | [GigaParts](https://www.gigaparts.com) |
| **2.42" SSD1309 OLED** | Flight display | [Amazon](https://www.amazon.com/dp/B0CFF46319) |
| **Bluetooth Speaker** | Voice alerts | Any BT speaker |
| **Dupont Jumper Wires (120x)** | I2C connections | [Amazon](https://www.amazon.com/dp/B0B2L66ZFM) |
| **USB-C Power Supply** | Pi 5 power (5.1V/5A) | Included in starter kit |

### Wiring the OLED

```
OLED Pin → Raspberry Pi Pin
─────────────────────────────
GND      → Pin 6 (GND)
VCC      → Pin 1 (3.3V)
SDA      → Pin 3 (GPIO2)
SCL      → Pin 5 (GPIO3)
```

**Diagram:**
```
┌─────────────────────────────┐
│     Raspberry Pi 5          │
├─────────────────────────────┤
│ Pin 1  ├─────→ 3.3V (VCC)   │
│ Pin 3  ├─────→ SDA          │
│ Pin 5  ├─────→ SCL          │
│ Pin 6  ├─────→ GND          │
└─────────────────────────────┘
        ↓
    OLED Display
```

**Verify connection:**
```bash
i2cdetect -y 1
# Should show "3c" in the grid
```

---

## 🔊 Voice Alerts

### TTS Engine Selection

PiRadar uses **Coqui TTS** for offline speech synthesis (or **gTTS** with internet):

#### Option 1: **Coqui TTS** (Recommended - Offline) ⭐

✅ Works completely offline  
✅ High quality, natural voice  
✅ No internet required after first model download  

```bash
# Already included in requirements.txt
pip install -r requirements.txt
```

#### Option 2: **gTTS** (Online)

✅ Slightly more natural voice  
⚠️ Requires internet connection  
⚠️ Slower (1-2s per announcement)  

To switch, edit `main.py`:
```python
from text_to_speech import TextToSpeech
tts = TextToSpeech(volume=100, language="en-IN")  # en-IN = Indian English
```

#### Option 3: **pyttsx3** (Fallback)

✅ Fully offline  
⚠️ More robotic voice  

Automatically used if Coqui/gTTS unavailable.

---

## ⚙️ Configuration

Edit `config.toml` to customize:

```toml
[api_keys]
opensky_client_id = "YOUR_ID"
opensky_client_secret = "YOUR_SECRET"
flightaware_aeroapi_key = ""      # Leave blank to disable
airportdb_api_token = ""

[common]
latitude = 29.7604               # Houston example
longitude = -95.3698
radius_miles = 30
poll_interval_seconds = 10
cooldown_minutes = 15            # Alert cooldown per flight
alert_volume = 0.8

# Quiet hours (snooze)
snooze_start_time = "22:00"      # 10 PM
snooze_end_time = "07:00"        # 7 AM

# Text-to-speech
enable_airline_announcement = true
announcement_delay_seconds = 0.5

# FlightAware usage cap
monthly_call_limit = 0           # 0 = disabled
```

---

## 📡 API Setup

### OpenSky Network (Free, Required)

1. Sign up: https://opensky-network.org/data/api
2. Create credentials
3. Add to `config.toml`:
```toml
opensky_client_id = "YOUR_ID"
opensky_client_secret = "YOUR_SECRET"
```

### FlightAware AeroAPI (Optional, Paid)

Provides airline names, routes, aircraft type.

1. Sign up: https://www.flightaware.com/commercial/aeroapi/
2. Add credit card (usage-based pricing)
3. Get API key: https://www.flightaware.com/aeroapi/portal
4. Add to `config.toml`:
```toml
flightaware_aeroapi_key = "YOUR_KEY"
```

**💡 Pro tip:** Set `monthly_call_limit = 50` to cap costs at ~$1/month

### AirportDB (Free, Optional)

Airport name lookups (e.g., "Houston Hobby" instead of "HOU").

1. Sign up: https://airportdb.io/
2. Get API token
3. Add to `config.toml`:
```toml
airportdb_api_token = "YOUR_TOKEN"
```

---

## 🐧 Raspberry Pi Setup

### 1. Flash OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/):
- OS: **Raspberry Pi OS Lite** (64-bit recommended)
- Username: `pi`
- Enable SSH
- Configure WiFi

### 2. First Boot

```bash
sudo apt update && sudo apt upgrade -y
```

### 3. Enable I2C (for OLED)

```bash
sudo raspi-config
# Interface Options → I2C → Enable → Finish
sudo reboot
```

### 4. Verify I2C

```bash
sudo apt install -y i2c-tools
i2cdetect -y 1
# Look for "3c" in the grid
```

### 5. Install PiRadar

```bash
cd ~
git clone https://github.com/haidevaraj/PiRadar.git
cd PiRadar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml
# Edit config.toml with your API keys and location
python3 main.py
```

---

## 🤖 Bluetooth Speaker Setup

### Pair Speaker

```bash
bluetoothctl
```

Inside bluetoothctl shell:
```
power on
scan on
# Wait for speaker to appear
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
connect AA:BB:CC:DD:EE:FF
exit
```

### Test Audio

```bash
paplay /usr/share/sounds/alsa/Front_Center.wav
```

Should hear sound from speaker! ✅

---

## 🔄 Auto-Start on Boot

### Create Systemd Service

```bash
sudo nano /etc/systemd/system/PiRadar.service
```

Paste:
```ini
[Unit]
Description=PiRadar Flight Tracker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/PiRadar
ExecStart=/home/pi/PiRadar/.venv/bin/python /home/pi/PiRadar/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Enable Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable PiRadar.service
sudo systemctl start PiRadar.service
```

### View Logs

```bash
sudo journalctl -u PiRadar.service -f
```

**Useful commands:**
```bash
sudo systemctl status PiRadar.service
sudo systemctl stop PiRadar.service
sudo systemctl restart PiRadar.service
```

---

## 🎨 Display Features

### Alert Screen
When a flight is detected:
```
┌────────────────────────────────┐
│  UAL1234                       │  ← Callsign
│  Houston IAH → Denver DEN      │  ← Route
│  SPD: 450kt  HDG: 315°  ALT:35K │  ← Flight data
│  VS: 1200fpm ▲                 │  ← Vertical speed
└────────────────────────────────┘
```

### Idle Screen
Shows rotating airplane facts while waiting for flights.

### Snooze Indicator
Displays "SNOOZED UNTIL 7:00 AM" during quiet hours.

---

## 📊 Alert Behavior

When a new flight enters your detection radius:

1. 🔊 **Alert sound plays** (chime.mp3 or alert.mp3)
2. 📱 **OLED shows flight details**
3. 🗣️ **Voice announcement** (if enabled)
   - "Flight alert: United Airlines. From Houston IAH to Denver DEN."
4. 📝 **Logged to console**

**Squawk codes:**
- `7700` → Emergency (plays alert.mp3)
- `7500` → Hijack (plays alert.mp3)
- Others → Normal (plays chime.mp3)

**Cooldown:** Same callsign won't re-alert for `cooldown_minutes` (default: 15)

---

## 🛠️ Troubleshooting

### OLED Not Showing

```bash
# Check I2C connection
i2cdetect -y 1
# Should show "3c"

# Check wiring: GND, VCC, SDA, SCL
# Try raising Pi I2C voltage to 5V (if display supports it)
```

### No Audio/Bluetooth Not Working

```bash
# Check speaker is paired
bluetoothctl devices

# Restart PulseAudio
pulseaudio --kill
pulseaudio --start

# Test audio
paplay /usr/share/sounds/alsa/Front_Center.wav
```

### API Errors

```bash
# Check OpenSky credentials
curl -u YOUR_ID:YOUR_SECRET "https://opensky-network.org/api/states/all"
# Should return JSON

# Check FlightAware key
curl -H "x-apikey: YOUR_KEY" "https://aeroapi.flightaware.com/aeroapi/me"
```

### High CPU Usage

```bash
# Increase poll_interval_seconds in config.toml
# Default is 10 seconds, try 30 or 60
```

---

## 📦 Dependencies

```
pygame==2.5.2          # Audio playback
requests==2.31.0       # HTTP client
pydantic==2.4.2        # Config validation
TTS==0.22.0            # Coqui TTS (offline speech)
pyttsx3==2.90          # Fallback TTS
gTTS==2.3.1            # Google TTS (optional)
```

See `requirements.txt` for full list.

---

## 📝 License

**Source-available for personal/hobbyist use only.**

You may NOT use this project for commercial purposes without written permission.

See [LICENSE.md](LICENSE.md) for full terms.

**Original author:** [A.J. Harnak](https://github.com/ajharnak/flighttrackr)  
**Fork author:** [haidevaraj](https://github.com/haidevaraj)

---

## ☕ Support

If you find PiRadar useful, consider supporting the original author:

[Buy A.J. Harnak a coffee](https://buymeacoffee.com/ajharnak) ☕

---

## 🐛 Contributing

Found a bug? Want a feature?

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-idea`)
3. Commit changes (`git commit -am 'Add amazing idea'`)
4. Push to branch (`git push origin feature/amazing-idea`)
5. Open a Pull Request

---

## 📚 Resources

- [OpenSky API Docs](https://opensky-network.org/apidoc/)
- [FlightAware AeroAPI](https://www.flightaware.com/aeroapi/portal/)
- [Raspberry Pi Docs](https://www.raspberrypi.com/documentation/)
- [Coqui TTS](https://github.com/coqui-ai/TTS)

---

**Happy tracking! 🛩️✈️**
