# FlightTrackr

FlightTrackr watches nearby OpenSky traffic and logs a quick alert when a new flight enters your monitoring area. Audio alerts use `pygame` so the mixer can stay open between alerts, which is helpful on Raspberry Pi setups that pop when the audio device repeatedly powers up and down.

## What it does

- Polls OpenSky for aircraft inside a small box around your chosen latitude and longitude
- Alerts once per callsign, then suppresses repeats for your configured cooldown window
- Pauses normal polling during your configured snooze hours
- Uses FlightAware only for callsigns that look like known airlines, which avoids spending API calls on many local GA flights
- Stops FlightAware enrichment entirely once your configured monthly cap is reached
- Plays the stronger `alert.mp3` sound for squawk `7700` or `7500`, and `chime.mp3` for normal alerts
- Shows active alerts on the OLED, then rotates airplane facts while idle

## What you need

- Python 3.11+
- `pip`
- An OpenSky Network API client ID and client secret
- A working audio output on your Raspberry Pi or Linux system
- Optional: a 2.42" SSD1309 OLED over I2C

## Hardware used for the author's build

This project was built around a Raspberry Pi 1 Model B+ running Raspberry Pi OS Lite (formerly Raspbian Lite). Because that Pi does not have built-in Wi-Fi, it also uses a USB Wi-Fi adapter.

The original build used:

- Raspberry Pi 1 Model B+
- 2.42" SSD1309 128x64 OLED over I2C
- Small external speaker
- Small 5V amplifier board
- USB Wi-Fi dongle
- Assorted Dupont jumper wires

Parts linked from the original build:

- OLED display: `https://www.amazon.com/dp/B0CFF46319`
- Speaker: `https://www.amazon.com/dp/B0FBRVCZQ6`
- Amplifier: `https://www.amazon.com/dp/B0912CWB7Z`
- Wi-Fi dongle: `https://www.amazon.com/dp/B0BNFKJPXS`
- Jumper wires: `https://www.amazon.com/dp/B0B2L66ZFM`

The OLED listing resolves to a HiLetgo-style 2.42" SSD1309 128x64 module with a 4-pin I2C header. The jumper wire kit resolves to a standard 120-wire Dupont assortment. The other linked parts were used in the original build, but the exact Amazon product text was not easily recoverable when this README was updated, so the wiring guidance below stays generic where needed.

## Hardware assembly

### 1. Wire the OLED

For a 4-pin I2C SSD1309 OLED:

- OLED `GND` -> Pi physical pin `6` (`GND`)
- OLED `VDD` or `VCC` -> Pi physical pin `1` (`3.3V`)
- OLED `SCL` -> Pi physical pin `5` (`GPIO3 / SCL1`)
- OLED `SDA` -> Pi physical pin `3` (`GPIO2 / SDA1`)

This project expects the display on I2C bus `1` at address `0x3C`, which is the default in `config.toml`.

OLED wiring summary:

| OLED pin | Raspberry Pi pin | Physical pin | Notes |
| --- | --- | --- | --- |
| `GND` | `GND` | `6` | Ground |
| `VCC` / `VDD` | `3.3V` | `1` | The author's screen is powered from `3.3V` |
| `SDA` | `GPIO2 / SDA1` | `3` | I2C data |
| `SCL` | `GPIO3 / SCL1` | `5` | I2C clock |

### 2. Wire the amplifier and speaker

Do not connect a speaker directly to the Pi GPIO pins.

The author's build does not use the Pi's 3.5mm audio jack.

The amp is wired to Raspberry Pi physical pins `2`, `3`, `4`, `6`, `12`, `35`, and `40`.

That means the author's build uses GPIO-side digital audio wiring, with the amp powered from `5V` and the OLED separately powered from `3.3V`.

Author's reported amp wiring:

- Pi physical pin `2` (`5V`) -> amplifier power
- Pi physical pin `4` (`5V`) -> amplifier power
- Pi physical pin `6` (`GND`) -> amplifier ground
- Pi physical pin `12` (`GPIO18`) -> amplifier audio signal
- Pi physical pin `35` (`GPIO19`) -> amplifier audio signal
- Pi physical pin `40` (`GPIO21`) -> amplifier audio signal
- Pi physical pin `3` (`GPIO2`) -> extra amp connection used in the author's build
- Amplifier speaker output -> speaker terminals

If your speaker is mono, use a single amplifier channel only. Do not tie the left and right amp outputs together.

The original build used a small 5V mini amp board. Based on the reported GPIO wiring, it behaves more like a digital-audio amp module than a simple 3.5mm-input analog amp. Because I could not fully recover the exact Amazon listing details for that board, you should match these Pi pins against the labels printed on your amplifier board before powering it up.

Amplifier wiring summary:

| Amplifier side | Raspberry Pi connection | Physical pin | Notes |
| --- | --- | --- | --- |
| Power input | `5V` | `2` and `4` | The author's amp is powered from `5V` |
| Ground | `GND` | `6` | Shared ground |
| Audio/control | `GPIO18` | `12` | Used by the author's amp wiring |
| Audio/control | `GPIO19` | `35` | Used by the author's amp wiring |
| Audio/control | `GPIO21` | `40` | Used by the author's amp wiring |
| Extra board-specific line | `GPIO2` | `3` | Present in the author's build; verify against your board labels |
| Speaker output | Speaker terminals | n/a | Use one channel for mono if needed |

### Wiring diagram

```text
Raspberry Pi 1 B+                    OLED (SSD1309 I2C)
------------------                   ------------------
Pin 1  (3.3V)  --------------------> VCC / VDD
Pin 3  (GPIO2 SDA1) ---------------> SDA
Pin 5  (GPIO3 SCL1) ---------------> SCL
Pin 6  (GND)   --------------------> GND

Raspberry Pi 1 B+                    Amplifier
------------------                   ------------------
Pin 2  (5V)   ---------------------> Power
Pin 4  (5V)   ---------------------> Power
Pin 6  (GND)  ---------------------> GND
Pin 12 (GPIO18) -------------------> Signal
Pin 35 (GPIO19) -------------------> Signal
Pin 40 (GPIO21) -------------------> Signal
Pin 3  (GPIO2)  -------------------> Extra board-specific line

Amplifier                            Speaker
---------                            -------
Speaker output  --------------------> Speaker terminals
```

### 3. Add Wi-Fi

The Raspberry Pi 1 B+ needs a USB Wi-Fi adapter because it has no onboard wireless.

- Plug the Wi-Fi dongle into any USB port
- Configure Wi-Fi during Raspberry Pi OS imaging if possible
- If you set up the card first and boot later, you can still join Wi-Fi from the Pi once it is running

### 4. Power and enclosure notes

- Use a stable Pi power supply
- Keep the OLED on `3.3V`, not `5V`, unless your exact display board explicitly supports and expects `5V`
- The author's amp is powered from `5V`
- Keep jumper wires short and tidy around the OLED to reduce intermittent I2C issues
- Mount the speaker so it can vent sound; tiny speakers sound much worse when sealed badly

## Raspberry Pi setup

### 1. Flash the OS

Use Raspberry Pi Imager and install Raspberry Pi OS Lite.

Helpful options to set during imaging:

- hostname
- Wi-Fi SSID and password
- SSH enabled
- username and password
- locale and timezone

### 2. First boot

After the Pi boots:

```bash
sudo apt update
sudo apt upgrade -y
```

### 3. Enable I2C

Run:

```bash
sudo raspi-config
```

Then enable:

- `Interface Options` -> `I2C` -> `Enable`

Reboot afterward:

```bash
sudo reboot
```

### 4. Verify the OLED is visible

Install I2C tools:

```bash
sudo apt install -y i2c-tools
```

Then scan bus 1:

```bash
i2cdetect -y 1
```

You should usually see `3c` in the grid if the OLED is wired correctly.

### 5. Install the app

Install the Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If your audio hardware pops at the start and end of each alert, add a silent looping MP3 at `assets/silent.mp3`. When present, FlightTrackr will keep that file playing at zero volume in the background so the audio path stays open.

On older Raspberry Pi hardware, `pip install` can take a while. A Pi 1 B+ is absolutely usable here, but it is slow by modern standards.

## Configuration

1. Copy the example config:

```bash
cp config.example.toml config.toml
```

2. Open `config.toml`.
3. Fill in your own API keys in `[api_keys]`.
4. Set your own `latitude` and `longitude` in `[common]`.
5. Adjust `radius_miles`, `cooldown_minutes`, `snooze_start_time`, `snooze_end_time`, and `alert_volume` to taste.

The top of `config.toml` is arranged for the settings most people care about first:

- `[api_keys]` for OpenSky, FlightAware, and AirportDB credentials
- `[common]` for location, radius, snooze hours, volume, usage caps, and the main OLED timing knobs
- advanced sections below for request timeouts, cache TTLs, logging, paths, and low-level display settings

The Python loader in `settings_loader.py` reads `config.toml` and then applies environment variables as overrides. That makes `config.toml` the easiest file for most users to edit, while still letting you keep secrets or deployment-specific values in env vars.

If `config.toml` is missing, the app will tell you to copy `config.example.toml` first.

### Required vs optional keys

- Fill in all four entries in `[api_keys]`
- This project is designed around OpenSky, FlightAware AeroAPI, and AirportDB all being configured

## API accounts you will need

### OpenSky

- Sign up and create API credentials: `https://opensky-network.org/data/api`
- Put them in `config.toml` as `opensky_client_id` and `opensky_client_secret`

### FlightAware AeroAPI

- Pricing and product page: `https://www.flightaware.com/commercial/aeroapi/`
- Developer portal: `https://www.flightaware.com/aeroapi/portal/account`
- Put the API key in `config.toml` as `flightaware_aeroapi_key`

Plan on needing billing setup for FlightAware. Their AeroAPI product is usage-based, and in practice you should expect to provide a credit card or other payment method when enabling it.

### AirportDB

- Sign up for an API token: `https://airportdb.io/`
- Put the token in `config.toml` as `airportdb_api_token`

Put all of your credentials directly into `config.toml`. That is the intended setup for this project and the simplest path for most users.

The default OLED settings in `config.toml` assume I2C bus `1`, address `0x3C`, and normal orientation. If your display uses a different I2C address or is mounted upside down, adjust those values in the display sections of `config.toml`.

## Run

```bash
python3 main.py
```

On a Raspberry Pi 1 B+, especially on Raspberry Pi OS Lite and older storage, it may take a few minutes after power-on before you see useful activity on the screen. The Pi has to boot Linux, bring up Wi-Fi, start Python, load the OLED stack, and make its first API calls. A blank or quiet screen for the first couple of minutes is not necessarily a failure.

## Start on boot

If you want FlightTrackr to launch automatically whenever the Pi powers on, set it up as a `systemd` service.

### 1. Find your project path

Example:

```bash
pwd
```

Assume the project lives at:

```text
/home/pi/flighttrackr
```

### 2. Create a service file

```bash
sudo nano /etc/systemd/system/flighttrackr.service
```

Paste this in, adjusting the paths and username if needed:

```ini
[Unit]
Description=FlightTrackr
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/flighttrackr
ExecStart=/home/pi/flighttrackr/.venv/bin/python /home/pi/flighttrackr/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 3. Enable the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable flighttrackr.service
sudo systemctl start flighttrackr.service
```

### 4. Check status

```bash
sudo systemctl status flighttrackr.service
```

### 5. View logs

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

This project is source-available for personal, hobbyist, educational, and other non-commercial use only.

You may not use this project, or a modified version of it, for commercial purposes without explicit written permission from the author.

This project is provided as-is, with no warranty of any kind. That includes no warranty for correctness, reliability, fitness for a particular purpose, hardware safety, API costs, or regulatory compliance. You are responsible for your own hardware, accounts, wiring, credentials, and operating costs.

See `LICENSE.md` for the full terms.
