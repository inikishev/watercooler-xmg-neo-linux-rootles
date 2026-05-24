Connect to XMG water cooler from linux. Should work with Yaoshi 16 Ultra X6AR55, Eluktronics Hydroc G2, XMG NEO 16 E25, Dream Machines RT50X0-16EU25, PCSPECIALIST 16" Recoil, Medion Erazer Beast 16 X1 Ultimate, TUXEDO Stellaris 16 - Gen7, UNIWILL ID* Series, CyberPower Tracer IX Edge Pro LC16 (they are all the same laptop)

read original readme for more info https://github.com/anvme/watercooler-xmg-neo-linux

this is a rootless version that works on Bazzite and all packages are actually already included in Bazzite so you don't need any `rpm-ostree`.

To install run `install-rootless.sh` instead of `install.sh`:

```bash
git clone https://github.com/inikishev/watercooler-xmg-neo-linux-rootles
cd watercooler-xmg-neo-linux-rootles
sudo bash install-rootless.sh
```

Then to start and connect to the cooler
```bash
systemctl --user start watercooler
```

To start on login (I havent tested if this works)
```bash
systemctl --user enable watercooler
```

see status:
```bash
systemctl --user status watercooler
```

view logs:
```bash
journalctl --user -u watercooler -f
```

also this works on mechrevo cooler.

Its installed in `~/.local/share/watercooler`. I've added that you can now edit `curve.conf` to change the fan and pump activation curve.

It looks like this by default:
```json
[
    [55, 25, "7"],
    [70, 50, "8"],
    [85, 75, "11"],
    [999, 90, "11"]
]
```
Note that this must be a valid JSON so last entry must not have a comma after it.

First number is max temperature in celsius, second is fan speed (up to 90), third is pumping power. Pumping power must be one of "0", "7", "8", "11", "12", where the bigger the number, the more power, and "0" means pump is off (I dont know why those numbers)

Changes you make are applied immediately.

Here is a curve to have it off when idle (under 60C) and at low power under 80C, otherwise at max power (use on ECO power plan this reduces temps by 10C while the pump is very quiet)
```json
[
    [60, 0, "0"],
    [80, 30, "7"],
    [999, 90, "12"]
]
```

this is my current curve
```json
[
    [60, 0, "0"],
    [75, 30, "7"],
    [80, 45, "8"],
    [85, 60, "11"],
    [999, 90, "12"]
]
```

You can also edit `watercooler.py` in that folder if you want, and apply changes by saying this:
```bash
systemctl --user restart watercooler
```