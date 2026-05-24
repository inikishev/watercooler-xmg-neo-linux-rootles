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
```
systemctl --user start watercooler
```

To start on login (I havent tested if this works)
```
systemctl --user enable watercooler
```

see status:
```
systemctl --user status watercooler
```

view logs:
```
journalctl --user -u watercooler -f
```

also this works on mechrevo cooler.