# SPDX-License-Identifier: GPL-2.0-or-later
import re
import struct
from collections import namedtuple

from protocol.base_protocol import BaseProtocol
from protocol.constants import CMD_VIA_LIGHTING_GET_VALUE

CMD_KEY_COLOURS = 0x55
KC_GET_INFO, KC_GET, KC_SET, KC_PREVIEW, KC_ERR = 0x01, 0x02, 0x03, 0x04, 0xFF
KC_PER_PACKET = 6
KC_PROTOCOL_VERSION = 1

VIALRGB_GET_NUMBER_LEDS = 0x43
VIALRGB_GET_LED_INFO = 0x44

COLOUR_RE = re.compile(r"^#[0-9a-fA-F]{6}\Z")

LedInfo = namedtuple("LedInfo", "x y flags row col")


class ProtocolKeyColours(BaseProtocol):
    key_colours_supported = False
    key_colours_layers = 0
    key_colours_led_count = 0
    key_colours_initialised = False
    key_colours = ()
    leds = ()

    def reload_key_colours(self):
        self.key_colours_supported = False
        self.key_colours_layers = 0
        self.key_colours_led_count = 0
        self.key_colours_initialised = False
        self.key_colours = []
        self.leds = []

        if not getattr(self, "lighting_vialrgb", False):
            return

        data = self.usb_send(self.dev, struct.pack("BB", CMD_KEY_COLOURS, KC_GET_INFO), retries=20)
        if data[0] != CMD_KEY_COLOURS or data[1] != KC_GET_INFO or data[2] != KC_PROTOCOL_VERSION:
            return
        layers = data[3]
        led_count = data[4] | (data[5] << 8)
        initialised = bool(data[6])
        if layers == 0 or led_count == 0:
            return

        data = self.usb_send(self.dev, struct.pack("BB", CMD_VIA_LIGHTING_GET_VALUE, VIALRGB_GET_NUMBER_LEDS),
                             retries=20)
        if (data[2] | (data[3] << 8)) != led_count:
            return

        leds = []
        for idx in range(led_count):
            data = self.usb_send(self.dev, struct.pack("<BBH", CMD_VIA_LIGHTING_GET_VALUE, VIALRGB_GET_LED_INFO, idx),
                                 retries=20)
            leds.append(LedInfo(data[2], data[3], data[4], data[5], data[6]))

        colours = []
        for layer in range(layers):
            row = []
            for start in range(0, led_count, KC_PER_PACKET):
                count = min(KC_PER_PACKET, led_count - start)
                data = self.usb_send(self.dev, struct.pack("BBBBB", CMD_KEY_COLOURS, KC_GET, layer, start, count),
                                     retries=20)
                if data[1] == KC_ERR:
                    raise RuntimeError("failed reading key colours layer {} led {}".format(layer, start))
                for i in range(count):
                    off = 5 + 4 * i
                    row.append((data[off + 1], data[off + 2], data[off + 3]) if data[off] else None)
            colours.append(row)

        self.leds = leds
        self.key_colours = colours
        self.key_colours_layers = layers
        self.key_colours_led_count = led_count
        self.key_colours_initialised = initialised
        self.key_colours_supported = True

    def set_key_colours(self, layer, changes):
        """ changes: {led: (r, g, b) or None}; contiguous runs are sent as one KC_SET of up to 6 entries """
        leds = sorted(changes)
        runs = []
        for led in leds:
            if runs and runs[-1][-1] == led - 1 and len(runs[-1]) < KC_PER_PACKET:
                runs[-1].append(led)
            else:
                runs.append([led])

        for run in runs:
            msg = struct.pack("BBBBB", CMD_KEY_COLOURS, KC_SET, layer, run[0], len(run))
            for led in run:
                c = changes[led]
                msg += struct.pack("BBBB", 0, 0, 0, 0) if c is None else struct.pack("BBBB", 1, c[0], c[1], c[2])
            data = self.usb_send(self.dev, msg, retries=20)
            if data[1] == KC_ERR:
                raise RuntimeError("failed setting key colours layer {} led {}".format(layer, run[0]))
            for led in run:
                c = changes[led]
                self.key_colours[layer][led] = None if c is None else tuple(c)
            self.key_colours_initialised = True

    def set_key_colours_preview(self, layer):
        value = 0xFF if layer is None else layer
        data = self.usb_send(self.dev, struct.pack("BBB", CMD_KEY_COLOURS, KC_PREVIEW, value), retries=20)
        if data[1] == KC_ERR:
            raise RuntimeError("failed setting key colours preview")

    def key_colours_to_json(self):
        return {
            "version": 1,
            "layers": [
                [None if c is None else "#{:02x}{:02x}{:02x}".format(*c) for c in layer]
                for layer in self.key_colours
            ]
        }

    def key_colours_from_json(self, data):
        try:
            if data["version"] != 1:
                return False
            layers = data["layers"]
            if not isinstance(layers, list) or any(not isinstance(layer, list) for layer in layers):
                return False
            if len(layers) != self.key_colours_layers:
                return False
            parsed = []
            for layer in layers:
                if len(layer) != self.key_colours_led_count:
                    return False
                row = []
                for c in layer:
                    if c is None:
                        row.append(None)
                    else:
                        if not isinstance(c, str) or not COLOUR_RE.match(c):
                            return False
                        row.append((int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)))
                parsed.append(row)
        except (KeyError, TypeError, ValueError):
            return False

        for idx, row in enumerate(parsed):
            self.set_key_colours(idx, dict(enumerate(row)))
        return True
