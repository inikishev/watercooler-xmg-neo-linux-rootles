# Linux LCT water cooler controller

Water cooler controller for linux that works on Bazzite (well at least Bazzite DX), compatible with XMG Oasis 1 (LCT21001) and Oasis 2 (LCT22002).

Heavily based on this [watercooler-xmg-neo-linux](https://github.com/anvme/watercooler-xmg-neo-linux)

## What it does

Every second (configurable) it reads temperatures of your laptop and sets fan and water pump speed based on the profile. This is the default profile:

```conf
# each line is 3 integers separated by a space - (max temp, fan speed, pump level)
# fan speed is up to 90, pump level 0 for pump off, 1 to 4 - on
60   0  0    # ≤60°C: fan off, pump off
75  30  1    # 60-75°C: fan 30, pump level 1
80  45  2    # 75-80°C: fan 45, pump level 2
85  60  3    # 80-85°C: fan 60, pump level 3
999 90  4    # >85°C: fan max, pump max
```

Note that the default profile is tuned for myself, and I use my laptop exclusively on ECO power plan (the green one), and I tuned it to be quiet and not annoy me, plus your hardware might be different, so you might need to tune it differently.

Because the sound of pump turning on is quite loud, I also made it so that it doesn't quickly turn on and off during short temperature spikes. First, pump and fan are only allowed to turn on after more than 50% of the last 15 seconds are above temperature threshold (60C in default profile). There is similar logic for turning them off. Secondly, a power level is only allowed to change once every 10 seconds (to avoid cycling it too quickly).

All of how it works is explained in more detail in the comments in `config.jsonc` where you can also configure everything.

It also is supposed to be able to control RBG. This part is just taken from watercooler-xmg-neo-linux and I've not tested it but it should work.

It also doesn't have a web UI like watercooler-xmg-neo-linux (I ran out of time this weekend and I also have too many other projects)

## Installation

run this command

```bash
bash install.sh
```

This copies files to `~/.local/share/watercooler/`, creates a python venv in it, and sets up a user systemd service.

After install:

```bash
# Start and enable the daemon
systemctl --user start watercooler

# View logs
journalctl --user -u watercooler -f

# Make it start on login (doesnt seem to work on bazzite)
systemctl --user enable watercooler
```

For some reason `systemctl --user enable watercooler` doesn't seem to work on bazzite, so you can add this line to `~/.bash_profile` to make it start automatically on log in (I've just thought of that fix and havent tested if it works):

```bash
systemctl --user start watercooler
```

## Manual run

Run without installing

```bash
uv run python watercooler.py daemon
```

Or with pip:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python watercooler.py daemon
```

## Configuration

### config.jsonc

Controls a bunch of settings. It explains all settings in its comments.

To change it after installing, go to `~/.local/share/watercooler/config.jsonc`, and there you can change it. Note that it reads that file every 60 seconds by default.  So you might need to wait  a little bit for changes to apply.

### Profiles

If you installed it go to `~/.local/share/watercooler/profiles`. You can create more profiles by creating new files with `.conf` extension, whose file name is the name of the profile. For example `my profile.conf`. And then you can select your profile in `config.jsonc`.

Each line: `max_temp fan_speed pump_level`, defining a stepwise curve. Example:

```
60   0  0    # ≤60°C: fan off, pump off
75  30  1    # 60-75°C: fan 30, pump level 1
80  45  2    # 75-80°C: fan 45, pump level 2
85  60  3    # 80-85°C: fan 60, pump level 3
999 90  4    # >85°C: fan max, pump max
```

Fan speed is in 0-90 range, where 0 means fan is off.

Pump levels: 0 (off), 1 (7V), 2 (8V), 3 (11V), 4 (12V). I think that V means voltage or something.

I found that fan speed 30 and pump level 1 (7V) is enough to get 10C lower temps while being quiet. And I've not actually seen any improvement from using highest fan and pump settings that are also very loud but I've also not tested it too much + I use ECO power plan which is already quite cool. If you use the other power plans you might benefit from more agressive settings.

### rgb.json

It should be explained in [watercooler-xmg-neo-linux](https://github.com/anvme/watercooler-xmg-neo-linux) where its copied from.

```json
{"mode": "static", "hex": "#00ffff"}
```

Modes: `static`, `breathe`, `rainbow`, `breathe-rainbow`, `off`.
