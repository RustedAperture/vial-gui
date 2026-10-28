import struct
import unittest

from protocol.keyboard_comm import Keyboard
from protocol.key_colours import LedInfo
from protocol.slider_targets import SliderTarget
from test.test_keyboard import SimulatedDevice


def make_kb(vialrgb=True):
    dev = SimulatedDevice()
    kb = Keyboard(dev, dev.sim_send)
    kb.lighting_vialrgb = vialrgb
    return kb, dev


def name12(name):
    return name.encode("ascii").ljust(12, b"\x00")


def expect_reload(dev, targets, current=0, flash=None):
    """ flash: None for version-1 firmware, else the mask a version-2 firmware reports. """
    dev.expect("5601", bytes([0x56, 0x01, 1 if flash is None else 2, 8, len(targets), current, 12]))
    for i, t in enumerate(targets):
        req = bytes([0x56, 0x02, i])
        dev.expect(req, req + bytes([t[0], t[1][0], t[1][1], t[1][2]]) + name12(t[2]))
    if flash is not None:
        dev.expect("5605", struct.pack("<BBI", 0x56, 0x05, flash))


def expect_flash(dev, mask):
    req = struct.pack("<BBI", 0x56, 0x06, mask)
    dev.expect(req, req)


def expect_set(dev, idx, t):
    req = bytes([0x56, 0x03, idx, t.control, t.colour[0], t.colour[1], t.colour[2]]) + name12(t.name)
    dev.expect(req, req)


def expect_count(dev, n):
    req = bytes([0x56, 0x04, n])
    dev.expect(req, req)


TARGETS = [SliderTarget(62, (255, 255, 255), "Slider"), SliderTarget(7, (1, 2, 3), "Vol")]


class TestSliderTargetsProtocol(unittest.TestCase):

    def loaded(self, current=0):
        kb, dev = make_kb()
        expect_reload(dev, [(62, (255, 255, 255), "Slider"), (7, (1, 2, 3), "Vol")], current)
        kb.reload_slider_targets()
        dev.finish()
        return kb, dev

    def test_unsupported_reply(self):
        kb, dev = make_kb()
        dev.expect("5601", "FF" * 32)
        kb.reload_slider_targets()
        dev.finish()
        self.assertIs(kb.slider_supported, False)
        self.assertEqual(kb.slider_targets, [])

    def test_wrong_version_unsupported(self):
        kb, dev = make_kb()
        dev.expect("5601", bytes([0x56, 0x01, 3, 8, 1, 0, 12]))
        kb.reload_slider_targets()
        dev.finish()
        self.assertIs(kb.slider_supported, False)

    def test_not_vialrgb_sends_nothing(self):
        kb, dev = make_kb(vialrgb=False)
        kb.reload_slider_targets()
        dev.finish()
        self.assertIs(kb.slider_supported, False)

    def test_reload(self):
        kb, dev = self.loaded(current=1)
        self.assertIs(kb.slider_supported, True)
        self.assertEqual(kb.slider_max, 8)
        self.assertEqual(kb.slider_name_max, 12)
        self.assertEqual(kb.slider_current, 1)
        self.assertEqual(kb.slider_targets, TARGETS)

    def test_reload_name_stops_at_nul_and_replaces_bad_bytes(self):
        kb, dev = make_kb()
        dev.expect("5601", bytes([0x56, 0x01, 1, 8, 1, 0, 12]))
        dev.expect("560200", bytes([0x56, 2, 0, 5, 9, 8, 7]) + b"A\xffB\x00junk" + b"\x00" * 4)
        kb.reload_slider_targets()
        dev.finish()
        self.assertEqual(kb.slider_targets[0].name, "A�B")

    def test_set_writes_each_then_count(self):
        kb, dev = self.loaded(current=1)
        new = [TARGETS[1], TARGETS[0], SliderTarget(1, (0, 0, 0), "")]
        for i, t in enumerate(new):
            expect_set(dev, i, t)
        expect_count(dev, 3)
        kb.set_slider_targets(new)
        dev.finish()
        self.assertEqual(kb.slider_targets, new)
        self.assertEqual(kb.slider_current, 1)

    def test_set_clamps_current(self):
        kb, dev = self.loaded(current=1)
        expect_set(dev, 0, TARGETS[0])
        expect_count(dev, 1)
        kb.set_slider_targets(TARGETS[:1])
        dev.finish()
        self.assertEqual(kb.slider_current, 0)

    def test_error_reply_raises(self):
        kb, dev = self.loaded()
        dev.expect(bytes([0x56, 0x03, 0, 62, 255, 255, 255]) + name12("Slider"),
                   bytes([0x56, 0xFF]))
        with self.assertRaises(RuntimeError):
            kb.set_slider_targets(TARGETS[:1])
        dev.finish()
        self.assertEqual(kb.slider_targets, TARGETS)

    def test_invalid_raises_before_sending(self):
        kb, dev = self.loaded()
        bad = [
            [],
            [TARGETS[0]] * 9,
            [SliderTarget(62, (255, 255, 255), "x" * 13)],
            [SliderTarget(62, (255, 255, 255), "café")],
            [SliderTarget(128, (255, 255, 255), "a")],
            [SliderTarget(-1, (255, 255, 255), "a")],
            [SliderTarget(1, (256, 0, 0), "a")],
            [SliderTarget(1, (0, 0), "a")],
            [SliderTarget(True, (0, 0, 0), "a")],
        ]
        for b in bad:
            with self.assertRaises(ValueError):
                kb.set_slider_targets(b)
        dev.finish()
        self.assertEqual(kb.slider_targets, TARGETS)

    def test_to_json(self):
        kb, dev = self.loaded()
        self.assertEqual(kb.slider_targets_to_json(), {
            "version": 1,
            "targets": [{"control": 62, "colour": "#ffffff", "name": "Slider"},
                        {"control": 7, "colour": "#010203", "name": "Vol"}]})

    def test_from_json_round_trip(self):
        kb, dev = self.loaded()
        data = kb.slider_targets_to_json()
        data["targets"][1]["colour"] = "#0A0b0C"
        expect_set(dev, 0, TARGETS[0])
        expect_set(dev, 1, SliderTarget(7, (10, 11, 12), "Vol"))
        expect_count(dev, 2)
        self.assertIs(kb.slider_targets_from_json(data), True)
        dev.finish()

    def test_from_json_invalid_sends_nothing(self):
        kb, dev = self.loaded()
        good = {"control": 1, "colour": "#000000", "name": "a"}

        def t(**kw):
            d = dict(good)
            d.update(kw)
            return d

        bad = [
            None, [], {}, {"version": 2, "targets": [good]},
            {"version": 1}, {"version": 1, "targets": []},
            {"version": 1, "targets": "x"},
            {"version": 1, "targets": [good] * 9},
            {"version": 1, "targets": [1]},
            {"version": 1, "targets": [{"control": 1}]},
            {"version": 1, "targets": [t(control=128)]},
            {"version": 1, "targets": [t(control=-1)]},
            {"version": 1, "targets": [t(control="1")]},
            {"version": 1, "targets": [t(control=True)]},
            {"version": 1, "targets": [t(colour="#12345")]},
            {"version": 1, "targets": [t(colour="#12345g")]},
            {"version": 1, "targets": [t(colour="#1234567\n")]},
            {"version": 1, "targets": [t(colour=5)]},
            {"version": 1, "targets": [t(name="x" * 13)]},
            {"version": 1, "targets": [t(name="café")]},
            {"version": 1, "targets": [t(name=3)]},
        ]
        for b in bad:
            self.assertIs(kb.slider_targets_from_json(b), False, b)
        dev.finish()


RAW = [(62, (255, 255, 255), "Slider"), (7, (1, 2, 3), "Vol")]


def leds(n):
    return [LedInfo(i, 0, 4, 0, i) for i in range(n)]


class TestSliderFlashProtocol(unittest.TestCase):

    def loaded(self, flash=0x7FFFFFFF, n_leds=31):
        kb, dev = make_kb()
        kb.leds = leds(n_leds)
        expect_reload(dev, RAW, flash=flash)
        kb.reload_slider_targets()
        dev.finish()
        return kb, dev

    def test_version_1_has_no_flash(self):
        kb, dev = make_kb()
        expect_reload(dev, RAW)
        kb.reload_slider_targets()
        dev.finish()
        self.assertIs(kb.slider_supported, True)
        self.assertIs(kb.slider_flash_supported, False)
        self.assertNotIn("flash_leds", kb.slider_targets_to_json())

    def test_version_2_reads_mask(self):
        kb, dev = self.loaded(flash=0x12345678)
        self.assertIs(kb.slider_supported, True)
        self.assertIs(kb.slider_flash_supported, True)
        self.assertEqual(kb.slider_flash_mask, 0x12345678)
        self.assertEqual(kb.slider_targets, TARGETS)

    def test_get_flash_error_raises(self):
        kb, dev = make_kb()
        dev.expect("5601", bytes([0x56, 0x01, 2, 8, 0, 0, 12]))
        dev.expect("5605", bytes([0x56, 0xFF]))
        with self.assertRaises(RuntimeError):
            kb.reload_slider_targets()
        dev.finish()
        self.assertIs(kb.slider_supported, False)
        self.assertIs(kb.slider_flash_supported, False)

    def test_set_mask(self):
        kb, dev = self.loaded()
        expect_flash(dev, 0x00010203)
        kb.set_slider_flash_mask(0x00010203)
        dev.finish()
        self.assertEqual(kb.slider_flash_mask, 0x00010203)

    def test_set_mask_error_keeps_mask(self):
        kb, dev = self.loaded()
        dev.expect(struct.pack("<BBI", 0x56, 0x06, 5), bytes([0x56, 0xFF]))
        with self.assertRaises(RuntimeError):
            kb.set_slider_flash_mask(5)
        dev.finish()
        self.assertEqual(kb.slider_flash_mask, 0x7FFFFFFF)

    def test_set_mask_invalid_sends_nothing(self):
        kb, dev = self.loaded()
        for bad in (-1, 1 << 32, "1", True, None):
            with self.assertRaises(ValueError):
                kb.set_slider_flash_mask(bad)
        dev.finish()

    def test_set_mask_unsupported_raises(self):
        kb, dev = make_kb()
        expect_reload(dev, RAW)
        kb.reload_slider_targets()
        with self.assertRaises(RuntimeError):
            kb.set_slider_flash_mask(1)
        dev.finish()

    def test_to_json_lists_leds(self):
        kb, dev = self.loaded(flash=0b1000101)
        self.assertEqual(kb.slider_targets_to_json()["flash_leds"], [0, 2, 6])

    def test_to_json_only_existing_leds(self):
        # firmware default 0xFFFFFFFF on a keyboard with fewer LEDs
        kb, dev = self.loaded(flash=0xFFFFFFFF, n_leds=3)
        self.assertEqual(kb.slider_targets_to_json()["flash_leds"], [0, 1, 2])

    def test_from_json_writes_mask_after_targets(self):
        kb, dev = self.loaded()
        data = kb.slider_targets_to_json()
        data["flash_leds"] = [30, 1, 17]
        expect_set(dev, 0, TARGETS[0])
        expect_set(dev, 1, TARGETS[1])
        expect_count(dev, 2)
        expect_flash(dev, (1 << 30) | (1 << 17) | 2)
        self.assertIs(kb.slider_targets_from_json(data), True)
        dev.finish()
        self.assertEqual(kb.slider_flash_mask, (1 << 30) | (1 << 17) | 2)

    def test_from_json_without_flash_leaves_mask(self):
        kb, dev = self.loaded(flash=0x55)
        data = kb.slider_targets_to_json()
        del data["flash_leds"]
        expect_set(dev, 0, TARGETS[0])
        expect_set(dev, 1, TARGETS[1])
        expect_count(dev, 2)
        self.assertIs(kb.slider_targets_from_json(data), True)
        dev.finish()
        self.assertEqual(kb.slider_flash_mask, 0x55)

    def test_from_json_flash_on_version_1_firmware_ignored(self):
        kb, dev = make_kb()
        expect_reload(dev, RAW)
        kb.reload_slider_targets()
        data = kb.slider_targets_to_json()
        data["flash_leds"] = [0, 1]
        expect_set(dev, 0, TARGETS[0])
        expect_set(dev, 1, TARGETS[1])
        expect_count(dev, 2)
        self.assertIs(kb.slider_targets_from_json(data), True)
        dev.finish()

    def test_from_json_invalid_flash_sends_nothing(self):
        kb, dev = self.loaded(n_leds=31)
        for bad in ("x", 3, [-1], [31], [32], ["1"], [True], [1.0], None):
            data = kb.slider_targets_to_json()
            data["flash_leds"] = bad
            self.assertIs(kb.slider_targets_from_json(data), False, bad)
        dev.finish()
        self.assertEqual(kb.slider_flash_mask, 0x7FFFFFFF)

    def test_from_json_flash_limit_32_without_led_info(self):
        kb, dev = self.loaded(n_leds=0)
        data = kb.slider_targets_to_json()
        self.assertEqual(data["flash_leds"], list(range(31)))
        data["flash_leds"] = [32]
        self.assertIs(kb.slider_targets_from_json(data), False)
        dev.finish()


if __name__ == "__main__":
    unittest.main()
