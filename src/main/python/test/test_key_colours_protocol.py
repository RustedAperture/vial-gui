import struct
import unittest

from protocol.keyboard_comm import Keyboard
from test.test_keyboard import SimulatedDevice


def make_kb(vialrgb=True):
    dev = SimulatedDevice()
    kb = Keyboard(dev, dev.sim_send)
    kb.lighting_vialrgb = vialrgb
    return kb, dev


def entry_bytes(entries):
    out = b""
    for e in entries:
        out += bytes([0, 0, 0, 0]) if e is None else bytes([1, e[0], e[1], e[2]])
    return out


def expect_reload(dev, layers, leds, colours, initialised=1):
    """ colours[layer][led] -> (r,g,b) or None """
    dev.expect("5501", struct.pack("<BBBBHB", 0x55, 0x01, 1, layers, leds, initialised))
    dev.expect("0843", struct.pack("<BBH", 0x08, 0x43, leds))
    for i in range(leds):
        dev.expect(struct.pack("<BBH", 0x08, 0x44, i),
                   bytes([0x08, 0x44, i * 10, i * 3, 4, i // 4, i % 4]))
    for layer in range(layers):
        start = 0
        while start < leds:
            n = min(6, leds - start)
            req = struct.pack("BBBBB", 0x55, 0x02, layer, start, n)
            dev.expect(req, req + entry_bytes(colours[layer][start:start + n]))
            start += n


class TestKeyColoursProtocol(unittest.TestCase):

    def test_unsupported_reply(self):
        kb, dev = make_kb()
        dev.expect("5501", "FF" * 32)
        kb.reload_key_colours()
        self.assertIs(kb.key_colours_supported, False)
        dev.finish()

    def test_wrong_version_unsupported(self):
        kb, dev = make_kb()
        dev.expect("5501", "5501" + "02020700" + "01")
        kb.reload_key_colours()
        self.assertIs(kb.key_colours_supported, False)
        dev.finish()

    def test_not_vialrgb_sends_nothing(self):
        kb, dev = make_kb(vialrgb=False)
        kb.reload_key_colours()
        self.assertIs(kb.key_colours_supported, False)
        dev.finish()

    def reloaded(self):
        kb, dev = make_kb()
        colours = [
            [(1, 2, 3), None, (4, 5, 6), None, None, None, (255, 255, 255)],
            [None] * 7,
        ]
        expect_reload(dev, 2, 7, colours)
        kb.reload_key_colours()
        return kb, dev, colours

    def test_reload_reads_info_leds_and_colours(self):
        kb, dev, colours = self.reloaded()
        dev.finish()
        self.assertIs(kb.key_colours_supported, True)
        self.assertEqual(kb.key_colours_layers, 2)
        self.assertEqual(kb.key_colours_led_count, 7)
        self.assertIs(kb.key_colours_initialised, True)
        self.assertEqual(kb.key_colours, colours)
        self.assertEqual(len(kb.leds), 7)
        self.assertEqual(tuple(kb.leds[2]), (20, 6, 4, 0, 2))
        self.assertEqual(kb.leds[5].row, 1)

    def test_set_groups_contiguous_runs(self):
        kb, dev, _ = self.reloaded()
        changes = {i: (i, i + 1, i + 2) for i in (0, 1, 2, 3, 4, 5, 6, 9)}
        changes[1] = None
        # led 9 is out of the 7 LED range in this fixture's cache; use a bigger board
        kb.key_colours_led_count = 10
        kb.key_colours[1] = [None] * 10
        for start, n in ((0, 6), (6, 1), (9, 1)):
            req = struct.pack("BBBBB", 0x55, 0x03, 1, start, n) + entry_bytes(
                [changes[i] for i in range(start, start + n)])
            dev.expect(req, req)
        kb.key_colours_initialised = False
        kb.set_key_colours(1, changes)
        dev.finish()
        self.assertIs(kb.key_colours_initialised, True)
        self.assertEqual(kb.key_colours[1][0], (0, 1, 2))
        self.assertIsNone(kb.key_colours[1][1])
        self.assertEqual(kb.key_colours[1][9], (9, 10, 11))

    def test_set_error_raises(self):
        kb, dev, _ = self.reloaded()
        req = struct.pack("BBBBB", 0x55, 0x03, 0, 2, 1) + entry_bytes([(9, 9, 9)])
        dev.expect(req, bytes([0x55, 0xFF]))
        with self.assertRaises(RuntimeError):
            kb.set_key_colours(0, {2: (9, 9, 9)})
        self.assertEqual(kb.key_colours[0][2], (4, 5, 6))

    def test_preview(self):
        kb, dev, _ = self.reloaded()
        dev.expect("550401", "550401")
        dev.expect("5504FF", "5504FF")
        kb.set_key_colours_preview(1)
        kb.set_key_colours_preview(None)
        dev.finish()

    def test_json_roundtrip_and_shape_mismatch(self):
        kb, dev, colours = self.reloaded()
        data = kb.key_colours_to_json()
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["layers"][0][0], "#010203")
        self.assertIsNone(data["layers"][0][1])
        self.assertEqual(data["layers"][0][6], "#ffffff")

        # roundtrip: layer 0 -> 6 + 1 entries, layer 1 -> 6 + 1 entries
        for layer in range(2):
            for start, n in ((0, 6), (6, 1)):
                req = struct.pack("BBBBB", 0x55, 0x03, layer, start, n) + entry_bytes(
                    colours[layer][start:start + n])
                dev.expect(req, req)
        self.assertTrue(kb.key_colours_from_json(data))
        dev.finish()

        three = {"version": 1, "layers": data["layers"] + [data["layers"][0]]}
        self.assertFalse(kb.key_colours_from_json(three))
        short = {"version": 1, "layers": [data["layers"][0][:6], data["layers"][1]]}
        self.assertFalse(kb.key_colours_from_json(short))
        self.assertFalse(kb.key_colours_from_json({"version": 2, "layers": data["layers"]}))
        self.assertFalse(kb.key_colours_from_json("junk"))
        dev.finish()


if __name__ == "__main__":
    unittest.main()
