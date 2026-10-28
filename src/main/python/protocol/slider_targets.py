# SPDX-License-Identifier: GPL-2.0-or-later
import re
import struct
from collections import namedtuple

from protocol.base_protocol import BaseProtocol

CMD_SLIDER_TARGETS = 0x56
ST_GET_INFO, ST_GET, ST_SET, ST_SET_COUNT, ST_ERR = 0x01, 0x02, 0x03, 0x04, 0xFF
ST_GET_FLASH, ST_SET_FLASH = 0x05, 0x06
ST_PROTOCOL_VERSIONS = (1, 2)
ST_FLASH_VERSION = 2      # first version with a selectable flash mask
ST_FLASH_MAX_LEDS = 32
ST_NAME_LEN = 12
ST_MAX_CONTROL = 127

COLOUR_RE = re.compile(r"^#[0-9a-fA-F]{6}\Z")

SliderTarget = namedtuple("SliderTarget", "control colour name")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


class ProtocolSliderTargets(BaseProtocol):
    slider_supported = False
    slider_max = 0
    slider_name_max = 0
    slider_targets = ()
    slider_current = 0
    slider_flash_supported = False
    slider_flash_mask = 0

    def reload_slider_targets(self):
        self.slider_supported = False
        self.slider_max = 0
        self.slider_name_max = 0
        self.slider_targets = []
        self.slider_current = 0
        self.slider_flash_supported = False
        self.slider_flash_mask = 0

        if not getattr(self, "lighting_vialrgb", False):
            return

        data = self.usb_send(self.dev, struct.pack("BB", CMD_SLIDER_TARGETS, ST_GET_INFO), retries=20)
        if data[0] != CMD_SLIDER_TARGETS or data[1] != ST_GET_INFO or data[2] not in ST_PROTOCOL_VERSIONS:
            return
        version = data[2]
        maximum, count, current, name_max = data[3], data[4], data[5], data[6]

        targets = []
        for idx in range(count):
            data = self.usb_send(self.dev, struct.pack("BBB", CMD_SLIDER_TARGETS, ST_GET, idx), retries=20)
            if data[1] == ST_ERR:
                raise RuntimeError("failed reading slider target {}".format(idx))
            raw = bytes(data[7:7 + ST_NAME_LEN]).split(b"\x00", 1)[0]
            targets.append(SliderTarget(data[3], (data[4], data[5], data[6]),
                                        raw.decode("ascii", errors="replace")))

        mask = 0
        if version >= ST_FLASH_VERSION:
            data = self.usb_send(self.dev, struct.pack("BB", CMD_SLIDER_TARGETS, ST_GET_FLASH), retries=20)
            if data[1] == ST_ERR:
                raise RuntimeError("failed reading the slider flash lights")
            mask = struct.unpack("<I", bytes(data[2:6]))[0]

        self.slider_max = maximum
        self.slider_name_max = name_max
        self.slider_targets = targets
        self.slider_current = current
        self.slider_supported = True
        self.slider_flash_supported = version >= ST_FLASH_VERSION
        self.slider_flash_mask = mask

    def _validate_slider_targets(self, targets):
        if not isinstance(targets, (list, tuple)) or not 1 <= len(targets) <= self.slider_max:
            raise ValueError("slider target count must be 1..{}".format(self.slider_max))
        encoded = []
        for t in targets:
            control, colour, name = t
            if not _is_int(control) or not 0 <= control <= ST_MAX_CONTROL:
                raise ValueError("slider control must be 0..{}".format(ST_MAX_CONTROL))
            if not isinstance(colour, (list, tuple)) or len(colour) != 3 or \
                    any(not _is_int(c) or not 0 <= c <= 255 for c in colour):
                raise ValueError("slider colour must be three ints 0..255")
            if not isinstance(name, str):
                raise ValueError("slider name must be a string")
            try:
                raw = name.encode("ascii")
            except UnicodeEncodeError:
                raise ValueError("slider name must be ASCII")
            if len(raw) > min(self.slider_name_max, ST_NAME_LEN):
                raise ValueError("slider name too long")
            encoded.append((control, tuple(colour), raw))
        return encoded

    def set_slider_targets(self, targets):
        encoded = self._validate_slider_targets(targets)

        for idx, (control, colour, raw) in enumerate(encoded):
            msg = struct.pack("BBBBBBB", CMD_SLIDER_TARGETS, ST_SET, idx, control, *colour)
            msg += raw.ljust(ST_NAME_LEN, b"\x00")
            data = self.usb_send(self.dev, msg, retries=20)
            if data[1] == ST_ERR:
                raise RuntimeError("failed setting slider target {}".format(idx))
        data = self.usb_send(self.dev, struct.pack("BBB", CMD_SLIDER_TARGETS, ST_SET_COUNT, len(encoded)),
                             retries=20)
        if data[1] == ST_ERR:
            raise RuntimeError("failed setting slider target count")

        self.slider_targets = [SliderTarget(c, col, raw.decode("ascii")) for c, col, raw in encoded]
        if self.slider_current >= len(encoded):
            self.slider_current = 0

    def set_slider_flash_mask(self, mask):
        """ Bit i set = LED i flashes when the slider target changes. """
        if not _is_int(mask) or not 0 <= mask < (1 << ST_FLASH_MAX_LEDS):
            raise ValueError("slider flash mask must be a 32-bit unsigned int")
        if not self.slider_flash_supported:
            raise RuntimeError("the keyboard can't choose which lights flash")
        data = self.usb_send(self.dev, struct.pack("<BBI", CMD_SLIDER_TARGETS, ST_SET_FLASH, mask), retries=20)
        if data[1] == ST_ERR:
            raise RuntimeError("failed setting the slider flash lights")
        self.slider_flash_mask = mask

    def _slider_flash_led_limit(self):
        leds = len(getattr(self, "leds", ()))
        return min(leds, ST_FLASH_MAX_LEDS) if leds else ST_FLASH_MAX_LEDS

    def slider_targets_to_json(self):
        data = {
            "version": 1,
            "targets": [
                {"control": t.control, "colour": "#{:02x}{:02x}{:02x}".format(*t.colour), "name": t.name}
                for t in self.slider_targets
            ]
        }
        if self.slider_flash_supported:
            data["flash_leds"] = [i for i in range(self._slider_flash_led_limit())
                                  if self.slider_flash_mask & (1 << i)]
        return data

    def slider_targets_from_json(self, data):
        try:
            if data["version"] != 1:
                return False
            entries = data["targets"]
            if not isinstance(entries, list):
                return False
            parsed = []
            for e in entries:
                colour = e["colour"]
                if not isinstance(colour, str) or not COLOUR_RE.match(colour):
                    return False
                parsed.append(SliderTarget(e["control"],
                                           (int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)),
                                           e["name"]))
            self._validate_slider_targets(parsed)
            mask = None
            if "flash_leds" in data:
                leds = data["flash_leds"]
                limit = self._slider_flash_led_limit()
                if not isinstance(leds, list) or any(not _is_int(i) or not 0 <= i < limit for i in leds):
                    return False
                mask = sum(1 << i for i in set(leds))
        except (KeyError, TypeError, ValueError, IndexError):
            return False

        self.set_slider_targets(parsed)
        if mask is not None and self.slider_flash_supported:
            self.set_slider_flash_mask(mask)
        return True
