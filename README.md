
                                  "Turn your Pi into a flight radar station"

## My Fork

This is a fork of [ajharnak/flighttrackr](https://github.com/ajharnak/flighttrackr) with the following additions:

### New Features
- **Text-to-Speech Support** — Audio alerts via Bluetooth speaker
- Configurable speech alerts for detected aircraft
## Text-to-Speech (TTS) Feature

This fork adds audio alerts using **Google Text-to-Speech (gTTS)** with a real human Indian female voice.

### TTS Engine
- **Primary:** gTTS v2.3.1 (Google Text-to-Speech - High quality, real human voice)
  - Language: English with Indian accent (`lang='en'`, `tld='co.in'`)
  - Provides realistic female voice for flight alerts
  
- **Fallback:** Coqui TTS (High-quality offline synthesis using VITS models)

### Installation
TTS dependencies are included in `requirements.txt`:
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
   - "Southwest Airlines SWA4389 Hartsfield Jackson Atlanta International Airport -> San Antonio International Airport. Cruising at 35,000 feet, 451 miles per hour, heading south."
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
journalctl -u flighttrackr.service -f
```

Useful service commands:

- Start: `sudo systemctl start flighttrackr.service`
- Stop: `sudo systemctl stop flighttrackr.service`
- Restart: `sudo systemctl restart flighttrackr.service`
- Disable autostart: `sudo systemctl disable flighttrackr.service`

## How FlightAware usage is minimized

- FlightAware is only queried for callsigns whose prefix matches a known airline in `assets/icao_to_airline_names.json`
- Callsign lookups are cached for a short time, so the same ident is not re-fetched immediately
- Re-alerts are suppressed by `cooldown_minutes`, so the same ident does not repeatedly trigger enrichments
- Snooze hours stop normal polling during quiet times
- `monthly_call_limit` hard-stops FlightAware usage when your cap is reached

This means you can still see nearby aircraft from OpenSky without necessarily spending a FlightAware lookup on every plane overhead.

## Alert behavior

When a new flight is detected inside the configured radius, the app will:

- Play `assets/chime.mp3` for normal alerts
- Play `assets/alert.mp3` for squawk `7700` or `7500`
- Log the flight details to the console
- Show alerts and system status on the OLED when enabled
- Render a dashboard-style alert layout with a callsign header, route/type detail line, and bottom widgets for `SPD`, `HDG`, `ALT`, and `VS`
- Translate common aircraft type codes into friendlier names via `assets/aircraft_types.json`

If FlightAware is configured and the callsign looks like a known airline, the alert may also include:

- origin and destination airports
- a cleaned-up aircraft type like `CRJ-900` instead of a longer manufacturer-prefixed label

When the display is idle, it rotates airplane facts in random order without repeats until the full fact list has been shown.

## Notes

- If `pygame` cannot initialize the mixer, the app will keep running and log a warning instead of crashing.

## Author, license, and warranty

Author: A.J. Harnak

If you like this project, consider buying me a coffee - https://buymeacoffee.com/ajharnak . Totally optional but greatly appreciated!

This project is source-available for personal, hobbyist, educational, and other non-commercial use only.

You may not use this project, or a modified version of it, for commercial purposes without explicit written permission from the author.

This project is provided as-is, with no warranty of any kind. That includes no warranty for correctness, reliability, fitness for a particular purpose, hardware safety, API costs, or regulatory compliance. You are responsible for your own hardware, accounts, wiring, credentials, and operating costs.

See `LICENSE.md` for the full terms.
