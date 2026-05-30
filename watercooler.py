"""Water cooler service heavily based on https://github.com/anvme/watercooler-xmg-neo-linux"""
import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime
from enum import IntEnum
from operator import itemgetter
from pathlib import Path
from typing import Any, Literal, cast
import itertools
from bleak import BleakClient, BleakScanner
from collections.abc import Coroutine, Callable
ROOT = Path(__file__).parent
from jsonc_parser.parser import JsoncParser

LOGGING_LEVEL = logging.INFO
logger = logging.getLogger("watercooler")
logger.setLevel(LOGGING_LEVEL)
handler = logging.StreamHandler()
handler.setLevel(LOGGING_LEVEL)
logger.addHandler(handler)

LOGGING_LEVELS = {
    0: 50,
    1: logging.ERROR,
    2: logging.WARNING,
    3: logging.INFO,
    4: logging.DEBUG,
    5: 1
}

def notify(title: str, message: str):
    subprocess.run(["notify-send", title, message], check=False)

def log_error(message: str):
    notify("watercooler error!", message)
    logger.error(message)
    with open(ROOT / "errors.log", "a", encoding='utf-8') as f:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[ERROR]{now}\n{message}\n\n")

# === Enums ===

class RGBState(IntEnum):
    STATIC = 0x00
    BREATHE = 0x01
    COLORFUL = 0x02
    BREATHE_COLOR = 0x03

class PumpVoltageModes(IntEnum):
    OFF = 0xFE
    V7 = 0x02
    V8 = 0x03
    V11 = 0x00
    V12 = 0x01

class Commands:
    RESET = 0x19
    FAN = 0x1b
    PUMP = 0x1c
    RGB = 0x1e

class NordicUART:
    CHAR_TX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'


PumpLevel = Literal[0,1,2,3,4]

LEVEL_TO_VOLTAGE: dict[PumpLevel, PumpVoltageModes] = {
    0: PumpVoltageModes.OFF,
    1: PumpVoltageModes.V7,
    2: PumpVoltageModes.V8,
    3: PumpVoltageModes.V11,
    4: PumpVoltageModes.V12,
}

VOLTAGE_TO_LEVEL: dict[PumpVoltageModes, PumpLevel] = {v:k for k,v in LEVEL_TO_VOLTAGE.items()}

MAX_FAN = 90
MAX_PUMP_LEVEL = 4

RGB_MODE_MAP = {
    "static": RGBState.STATIC,
    "breathe": RGBState.BREATHE,
    "rainbow": RGBState.COLORFUL,
    "breathe-rainbow": RGBState.BREATHE_COLOR,
}

# === Device ===

DEVICE_NAMES = ['lct21001', 'lct22002']

class WaterCoolingDevice:
    def __init__(self):
        self.client: BleakClient | None = None

        self.pump_level: Literal[0,1,2,3,4] = 0
        self.fan_speed: int = 0
        self.rgb_is_on = False
        self.rgb_state: tuple[int, int, int, RGBState] = (0, 255, 255, RGBState.STATIC)

    async def scan(self) -> list[dict]:
        """Scan for devices matching `DEVICE_NAMES`."""
        devices = await BleakScanner.discover(return_adv=True)
        results = []
        for addr, (device, adv) in devices.items():
            if not device.name:
                continue
            name_lower = device.name.lower()
            if any(n in name_lower for n in DEVICE_NAMES):
                results.append({"uuid": device.address, "name": device.name, "rssi": adv.rssi or 0})
        return results

    async def connect(self, address: str):
        """Connect to a device."""
        self.client = BleakClient(address)
        await self.client.connect(timeout=5.0)
        await self.set_pump_level(0)
        await self.set_fan_speed(0)

    async def disconnect(self):
        if self.client and self.client.is_connected:
            try:
                await self._send(Commands.RESET, [0x00, 0x01, 0x00, 0x00, 0x00])
            except Exception as e:
                tb = ''.join(traceback.format_exception(e))
                log_error(f"Error when disconnecting:\n{tb}")
            await self.client.disconnect()
        self.client = None

    async def is_connected(self):
        return self.client is not None and self.client.is_connected


    async def _send(self, cmd, payload):
        if not self.client or not self.client.is_connected:
            raise RuntimeError("Not connected")
        data = bytearray([0xfe, cmd] + payload + [0xef])
        await self.client.write_gatt_char(NordicUART.CHAR_TX, data)

    async def _pump_on(self, voltage: PumpVoltageModes):
        await self._send(Commands.PUMP, [0x01, 60, voltage, 0x00, 0x00])

    async def _pump_off(self):
        await self._send(Commands.PUMP, [0x00, 0x00, 0x00, 0x00, 0x00])

    async def _fan_on(self, speed: int):
        await self._send(Commands.FAN, [0x01, speed, 0x00, 0x00, 0x00])

    async def _fan_off(self):
        await self._send(Commands.FAN, [0x00, 0x00, 0x00, 0x00, 0x00])


    async def set_pump_level(self, level: PumpLevel):
        logger.info("Setting pump level to %i", level)
        if level == 0: await self._pump_off()
        else: await self._pump_on(LEVEL_TO_VOLTAGE[level])
        self.pump_level = level

    async def set_fan_speed(self, speed: int):
        logger.info("Setting fan speed to %i", speed)
        if speed == 0: await self._fan_off()
        else: await self._fan_on(speed)
        self.fan_speed = speed


    async def rgb_on(self, r: int, g: int, b: int, mode: RGBState):
        self.rgb_state = (r,g,b,mode)
        self.rgb_is_on = True
        await self._send(Commands.RGB, [0x01, r, g, b, mode])

    async def lazy_rgb_on(self, r: int, g: int, b: int, mode: RGBState):
        if self.rgb_is_on and (r,g,b,mode) == self.rgb_state: return
        await self.rgb_on(r, g, b, mode)

    async def rgb_off(self):
        self.rgb_is_on = False
        await self._send(Commands.RGB, [0x00, 0x00, 0x00, 0x00, 0x00])

    async def lazy_rgb_off(self):
        if self.rgb_is_on is False: return
        await self.rgb_off()

    async def reset(self):
        self.pump_level: Literal[0,1,2,3,4] = 0
        self.fan_speed: int = 0
        self.rgb_is_on = False
        self.rgb_state = (0, 1, 1, RGBState.STATIC)
        await self._send(Commands.RESET, [0x00, 0x01, 0x00, 0x00, 0x00])

# === Temperature reading ===

def read_cpu_temp() -> tuple[float | None, str]:
    """Read highest CPU temp in celsius from thermal zones."""
    temps = []
    thermal_base = "/sys/class/thermal"
    if not os.path.isdir(thermal_base):
        return None, f'"{thermal_base}" doesn\'t exist'

    exceptions = []

    for entry in os.listdir(thermal_base):
        if not entry.startswith("thermal_zone"):
            continue

        try:
            type_path = os.path.join(thermal_base, entry, "type")
            temp_path = os.path.join(thermal_base, entry, "temp")
            with open(type_path, "r", encoding='utf-8') as f:
                zone_type = f.read().strip().lower()
            # prefer CPU/package zones, but collect all
            with open(temp_path, "r", encoding='utf-8') as f:
                t = int(f.read().strip()) / 1000.0
                if t > 0:
                    temps.append((zone_type, t))

        except (IOError, ValueError) as e:
            exceptions.append(e)
            continue

    if not temps:
        return None, 'Could not read any temperatures:\n\n' + '\n\n'.join(''.join(traceback.format_exception(e)) for e in exceptions)

    # prefer x86_pkg_temp, coretemp, or anything with "cpu"/"pkg" in name
    for keyword in ["pkg", "cpu", "core", "soc"]:
        for zone_type, t in temps:
            if keyword in zone_type:
                return t, zone_type

    # fallback: highest temp
    return max(t for _, t in temps), "Fallback to highest temp"


def read_rgb_conf() -> dict[str, Any]:
    """Read RGB config. Returns dict with 'mode' and optionally 'hex'."""
    with open(ROOT / "rgb.json", "r", encoding='utf-8') as f:
        return json.load(f)

async def apply_rgb_conf(device: WaterCoolingDevice, conf: dict):
    mode_str = conf.get("mode", "static")

    if mode_str == "off":
        await device.lazy_rgb_off()
        return

    rgb_mode = RGB_MODE_MAP.get(mode_str, RGBState.STATIC)
    if mode_str in ("rainbow", "breathe-rainbow"):
        await device.lazy_rgb_on(0, 0, 0, rgb_mode)
        return

    hex_color = conf.get("hex", "#00ffff").lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    await device.lazy_rgb_on(r, g, b, rgb_mode)


def _parse_profile_entry(line: str) -> tuple[int,int,int] | tuple[None, None, None]:
    comment_idx = line.find("#")
    if comment_idx != -1:
        line = line[:comment_idx]

    line = line.strip()
    if len(line) == 0: return None, None, None

    parts = line.split()
    if len(parts) != 3:
        log_error(f'ERROR: Line "{line}" in current profile is malformed. It must have three integers (max temp, fan speed, pump level) separated by space.')
        return None, None, None

    try:
        max_temp, fan_speed, pump_level = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        log_error(f'ERROR: Line "{line}" in current profile is malformed. It must have three integers (max temp, fan speed, pump level) separated by space.')
        return None, None, None

    if fan_speed > MAX_FAN:
        log_error(f'ERROR: Fan speed {fan_speed} in "{line}" in current profile is above maximum fan speed {MAX_FAN}.')
        fan_speed = MAX_FAN

    if not 0 <= pump_level <= MAX_PUMP_LEVEL:
        log_error(f'ERROR: Pump level {pump_level} in "{line}" in current profile incorrect, it must be an integer between 0 and {MAX_PUMP_LEVEL}.')
        pump_level = max(pump_level, 0)
        pump_level = min(pump_level, MAX_PUMP_LEVEL)

    return max_temp, fan_speed, pump_level


def load_profile(profile_name: str) -> list[tuple[int,int,PumpLevel]]:
    with open(ROOT / "profiles" / f"{profile_name}.conf", "r", encoding='utf-8') as f:
        text = f.read()
        while '  ' in text: text = text.replace('  ', ' ')
        lines = [_parse_profile_entry(l) for l in text.split('\n')]
        lines = [l for l in lines if l[0] is not None]
        if len(lines) == 0:
            log_error(f'ERROR: profiles "{profile_name}" has no valid lines.')
            lines = [(0, 0, 0)]

    return cast(list[tuple[int,int,PumpLevel]], sorted(lines, key=lambda x: x[0]))


def get_profile_entry_for_temp(profile: list[tuple[int,int,PumpLevel]], C: float) -> tuple[int,int,PumpLevel]:
    if len(profile) == 1:
        return profile[0]

    for max_temp, fan_speed, pump_level in profile:
        if C <= max_temp:
            return max_temp, fan_speed, pump_level

    return profile[-1]

KEYS_IN_SECONDS_GETTER = itemgetter(
    "hot_seconds_to_turn_pump_on",
    "hot_seconds_to_turn_fan_on",
    "cold_seconds_to_turn_pump_off",
    "cold_seconds_to_turn_fan_off",
)

class WaterCoolerDaemon:

    profile: list[tuple[int, int, PumpLevel]]
    """list of tuples `(max temp, fan speed, pump level)`, sorted by max temp."""

    def __init__(self):
        self.device = WaterCoolingDevice()
        self.config: dict[str, Any] | None = None
        self.config_last_updated = 0
        self.history_size = 0

        self.max_temp_pump_off = None
        self.max_temp_fan_off = None

        self.temps_history = []

        config, profile = self._load_config(time.time())

        self.t_ema_pump: float = config["ema_init_pump"]
        self.t_ema_fan: float = config["ema_init_fan"]

        self.last_updated_pump = 0
        self.last_updated_fan = 0
        self.last_updated_rgb = 0


    def _load_config(self, t: float) -> tuple[dict, list[tuple[int,int,PumpLevel]]]:
        if self.config is None or t - self.config_last_updated > self.config["config_update_frequency_seconds"]:

            # Load config
            self.config = JsoncParser.parse_file(ROOT / "config.jsonc")
            assert self.config is not None
            self.history_size = max(KEYS_IN_SECONDS_GETTER(self.config)) + 1

            self.rgb_config = read_rgb_conf()

            # Load profile
            self.profile = load_profile(self.config["profile"])

            for max_temp, fan_speed, pump_level in self.profile:
                if pump_level == 0: self.max_temp_pump_off = max_temp
                if fan_speed == 0: self.max_temp_fan_off = max_temp

            logging_level = LOGGING_LEVELS[self.config["logging_level"]]
            logger.setLevel(logging_level)
            handler.setLevel(logging_level)

            self.config_last_updated = time.time()

        return self.config, self.profile

    async def _connect(self):
        logger.info("Scanning for devices...")

        sleep_sec = 1
        retries = 6
        target = None
        for attempt in range(retries):

            devices = await self.device.scan()
            if devices:
                target = devices[0]["uuid"]
                logger.info("Found: %s [%s]", str(devices[0]['name']), str(target))
                logger.info("Connecting to %s...", str(target))
                await self.device.connect(target)
                logger.info("Connected.")
                return

            logger.warning("Scan attempt %i/%i — no device found", attempt+1, retries)
            await asyncio.sleep(sleep_sec)
            sleep_sec *= 2

        if target is None:
            log_error(f"Device not found after {retries} retries, waiting 30s...")
            await asyncio.sleep(30)

    def _update_emas(self, C: float, config: dict):

        ema_trigger_pump = config["ema_trigger_pump"]
        ema_trigger_fan = config["ema_trigger_fan"]

        beta_pump = 1 - 1 / 10 ** ema_trigger_pump
        beta_fan = 1 - 1 / 10 ** ema_trigger_fan

        self.t_ema_pump = self.t_ema_pump * beta_pump + C * (1 - beta_pump)
        self.t_ema_fan = self.t_ema_fan * beta_fan + C * (1 - beta_fan)


    async def _check_device_on(
        self,
        device: Literal["pump","fan"],
        level: int,
        max_temp_off: float | None,
        t_ema: float,
        hot_seconds_to_turn_on: float,
        hot_fraction_to_turn_on: float,
        set_fn: Callable[..., Coroutine],
    ) -> None:
        """Turn fan/pump on if conditions satisfied."""

        if max_temp_off is None:
            # there is no line with device off, it will always be on
            logger.debug("Turning %s on with level %i, as it is always on with current profile", device, level)
            await set_fn(level)
            return

        # check EMA first
        if t_ema >= max_temp_off:
            logger.debug("Turning %s on with level %i: t_ema = %f, >= %f", device, level, t_ema, max_temp_off)
            await set_fn(level)
            return

        # check enough temps in history
        n_temps = len(self.temps_history)
        if n_temps < hot_seconds_to_turn_on:
            logger.debug(
                "Not turning %s on with level %i because history has %i temps while hot_seconds_to_turn_on = %i",
                device, level, n_temps, hot_seconds_to_turn_on
            )
            return

        temps = self.temps_history[-hot_seconds_to_turn_on:]

        # last temp must be above threshold, and
        # hot_fraction_to_turn_on seconds must be above threshold
        if temps[-1] < max_temp_off:
            logger.debug("Not turning %s on with level %i: temps[-1] = %f, < %f", device, level, temps[-1], max_temp_off)
            return

        frac_above = len([t for t in temps if t >= max_temp_off]) / hot_seconds_to_turn_on

        if frac_above >= hot_fraction_to_turn_on:
            logger.debug("Turning %s on with level %i: frac_above = %f, >= %f", device, level, frac_above, hot_fraction_to_turn_on)
            await set_fn(level)
            return

        logger.debug("Not turning %s on with level %i: frac_above = %f, < %f", device, level, frac_above, hot_fraction_to_turn_on)

    async def _check_device_off(
        self,
        device: Literal["pump","fan"],
        max_temp_off: float | None,
        cold_seconds_to_turn_off: float,
        cold_fraction_to_turn_off: float,
        set_fn: Callable[..., Coroutine],
    ):
        """Turn fan/pump off if conditions satisfied, returns whether it was turned off."""

        if max_temp_off is None:
            # there is no line with device off, it will always be on
            logger.debug("Not turning %s off as it is always on with current profile", device)
            return

        # check enough temps in history
        n_temps = len(self.temps_history)
        if n_temps < cold_seconds_to_turn_off:
            logger.debug(
                "Not turning %s off because history has %i temps while cold_seconds_to_turn_off = %i",
                device, n_temps, cold_seconds_to_turn_off
            )
            return

        temps = self.temps_history[-cold_seconds_to_turn_off:]

        # last temp must be below threshold
        if temps[-1] > max_temp_off:
            logger.debug("Not turning %s off: temps[-1] = %f, > %f", device, temps[-1], max_temp_off)
            return

        frac_below = len([t for t in temps if t < max_temp_off]) / cold_seconds_to_turn_off

        if frac_below >= cold_fraction_to_turn_off:
            logger.debug("Turning %s off: frac_below = %f, >= %f", device, frac_below, cold_fraction_to_turn_off)
            await set_fn(0)
            return

        logger.debug("Not turning %s off: frac_below = %f, < %f", device, frac_below, cold_fraction_to_turn_off)



    async def step(self):
        t = time.time()

        config, profile = self._load_config(t)

        while not await self.device.is_connected():
            await self._connect()

        if len(profile) == 1:
            # if one line in profile, we don't need to read the temperature, the line always applies
            C = 0

        else:
            C, msg = read_cpu_temp()
            if C is None:
                log_error(f"Could not read CPU temperature:\n{msg}")
                C = 0

        self._update_emas(C, config)

        assert self.history_size != 0
        self.temps_history.append(C)
        while len(self.temps_history) > self.history_size:
            del self.temps_history[0]

        # find profile last line below current temp
        max_temp, fan_speed, pump_level = get_profile_entry_for_temp(profile, C)

        prev_pump_level = self.device.pump_level
        prev_fan_speed = self.device.fan_speed

        # ----------------------------------- pump ----------------------------------- #
        logger.log(1, "max_temp = %f, C = %f", max_temp, C)
        logger.log(1, "pump level: current = %i, requested = %i", self.device.pump_level, pump_level)
        logger.log(1, "fan speed: current = %i, requested = %i",  self.device.fan_speed, fan_speed)

        if self.device.pump_level == 0:
            if pump_level != 0:
                await self._check_device_on(
                    device = 'pump',
                    level = pump_level,
                    max_temp_off = self.max_temp_pump_off + config["pump_tolerance_on"],
                    t_ema = self.t_ema_pump,
                    hot_seconds_to_turn_on = config["hot_seconds_to_turn_pump_on"],
                    hot_fraction_to_turn_on = config["hot_fraction_to_turn_pump_on"],
                    set_fn = self.device.set_pump_level
                )

        else:
            if pump_level != self.device.pump_level:
                if pump_level == 0:
                    await self._check_device_off(
                        device = 'pump',
                        max_temp_off = self.max_temp_pump_off + config["pump_tolerance_off"],
                        cold_seconds_to_turn_off = config["cold_seconds_to_turn_pump_off"],
                        cold_fraction_to_turn_off = config["cold_fraction_to_turn_pump_off"],
                        set_fn = self.device.set_pump_level
                    )

                else:
                    if t - self.last_updated_pump > config["min_seconds_until_pump_level_change"]:
                        await self.device.set_pump_level(pump_level)


        # ------------------------------------ fan ----------------------------------- #
        if self.device.fan_speed == 0:
            if fan_speed != 0:
                await self._check_device_on(
                    device = 'fan',
                    level = fan_speed,
                    max_temp_off = self.max_temp_fan_off + config["fan_tolerance_on"],
                    t_ema = self.t_ema_fan,
                    hot_seconds_to_turn_on = config["hot_seconds_to_turn_fan_on"],
                    hot_fraction_to_turn_on = config["hot_fraction_to_turn_fan_on"],
                    set_fn = self.device.set_fan_speed
                )

        else:
            if fan_speed != self.device.fan_speed:
                if fan_speed == 0:
                    await self._check_device_off(
                        device = 'fan',
                        max_temp_off = self.max_temp_fan_off + config["fan_tolerance_off"],
                        cold_seconds_to_turn_off = config["cold_seconds_to_turn_fan_off"],
                        cold_fraction_to_turn_off = config["cold_fraction_to_turn_fan_off"],
                        set_fn = self.device.set_fan_speed
                    )

                else:
                    if t - self.last_updated_fan > config["min_seconds_until_fan_speed_change"]:
                        await self.device.set_fan_speed(fan_speed)


        if self.device.pump_level != prev_pump_level: self.last_updated_pump = t
        if self.device.fan_speed != prev_fan_speed: self.last_updated_fan = t

        if t - self.last_updated_rgb > config["config_update_frequency_seconds"]:

            await apply_rgb_conf(self.device, self.rgb_config)

    async def loop(self):
        assert self.config is not None

        while True:

            try:
                await self.step()

            except KeyboardInterrupt as e:
                raise e

            except Exception as e:
                tb = ''.join(traceback.format_exception(e))
                log_error(f"Error in daemon step, disconnecting:\n{tb}")
                try:
                    await self.device.disconnect()
                except Exception as e2:
                    tb = ''.join(traceback.format_exception(e2))
                    log_error(f"Error when disconnecting due to error:\n{tb}")
                await asyncio.sleep(5)

            await asyncio.sleep(self.config['poll_interval_seconds'])

    async def run(self):
        assert self.config is not None

        logger.info("Starting watercooler daemon")
        logger.info("Profile:\n%s", self.config['profile'])
        logger.info(self.profile)
        logger.info("Poll interval: %fs", self.config['poll_interval_seconds'])

        loop = asyncio.get_event_loop()
        stop = asyncio.Event()

        def handle_signal():
            logger.info("Shutting down...")
            stop.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, handle_signal)

        daemon_task = asyncio.create_task(self.loop())

        await stop.wait()
        daemon_task.cancel()
        try:
            await daemon_task
        except asyncio.CancelledError:
            pass
        logger.info("Stopped.")


def main():
    parser = argparse.ArgumentParser(description="Water Cooler Controller")
    parser.add_argument("command", nargs="?", default="daemon", choices=["daemon"],
                        help="Command to run (default: daemon)")
    args = parser.parse_args()

    if args.command == "daemon":
        daemon = WaterCoolerDaemon()
        asyncio.run(daemon.run())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Ctrl+C detected! Exiting program cleanly.")
        try:
            sys.exit(130)  # Standard exit code for Ctrl+C
        except SystemExit:
            os._exit(130)  # Hard exit if sys.exit hangs
