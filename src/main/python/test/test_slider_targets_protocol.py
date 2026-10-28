import struct
import unittest

from protocol.keyboard_comm import Keyboard
from protocol.slider_targets import SliderTarget
from test.test_keyboard import SimulatedDevice


def make_kb(vialrgb=True):
    dev = SimulatedDevice()
    kb = Keyboard(dev, dev.sim_send)
    kb.lighting_vialrgb = vialrgb
    return kb, dev


def name12(name):
    return name.encode("ascii").ljust(12, b"\x00")


def expect_reload(dev, targets, current=0):
    dev.expect("5601", bytes([0x56, 0x01, 1, 8, len(targets), current, 12]))
    for i, t in enumerate(targets):
        req = bytes([0x56, 0x02, i])
        dev.expect(req, req + bytes([t[0], t[1][0], t[1][1], t[1][2]]) + name12(t[2]))


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
        dev.expect("5601", bytes([0x56, 0x01, 2, 8, 1, 0, 12]))
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


if __name__ == "__main__":
    unittest.main()
