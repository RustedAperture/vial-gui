import json
import unittest
from unittest import mock

from test.test_slider_targets_protocol import make_kb, expect_reload, expect_set, expect_count, TARGETS


def vil_kb():
    kb, dev = make_kb()
    expect_reload(dev, [(62, (255, 255, 255), "Slider"), (7, (1, 2, 3), "Vol")])
    kb.reload_slider_targets()
    kb.key_colours_supported = False
    kb.keyboard_id = 1
    kb.layers = 0
    kb.rows = kb.cols = kb.encoder_count = 0
    kb.layout = {}
    kb.encoder_layout = {}
    kb.layout_options = 0
    kb.macro = b""
    kb.vial_protocol = kb.via_protocol = 0
    kb.tap_dance_entries = []
    kb.combo_entries = []
    kb.key_override_entries = []
    kb.alt_repeat_key_entries = []
    kb.tap_dance_count = kb.combo_count = kb.key_override_count = kb.alt_repeat_key_count = 0
    kb.settings = {}
    kb.macro_count = 0
    return kb, dev


def vil(kb, section, settings=None):
    data = json.loads(kb.save_layout().decode("utf-8"))
    if section is None:
        data.pop("slider_targets", None)
    else:
        data["slider_targets"] = section
    if settings is not None:
        data["settings"] = settings
    return json.dumps(data).encode("utf-8")


def good():
    return {"version": 1, "targets": [
        {"control": 62, "colour": "#ffffff", "name": "Slider"},
        {"control": 7, "colour": "#010203", "name": "Vol"}]}


def entry(control=1, colour="#000000", name="x"):
    return {"control": control, "colour": colour, "name": name}


class TestSliderTargetsVil(unittest.TestCase):

    def test_save_includes_targets(self):
        kb, dev = vil_kb()
        data = json.loads(kb.save_layout().decode("utf-8"))
        self.assertEqual(data["slider_targets"], good())

    def test_save_omits_when_unsupported(self):
        kb, dev = vil_kb()
        kb.slider_supported = False
        data = json.loads(kb.save_layout().decode("utf-8"))
        self.assertNotIn("slider_targets", data)

    def test_restore_writes(self):
        kb, dev = vil_kb()
        data = vil(kb, {"version": 1, "targets": [entry(5, "#0a0b0c", "Pad")]})
        t = TARGETS[0]._replace(control=5, colour=(10, 11, 12), name="Pad")
        expect_set(dev, 0, t)
        expect_count(dev, 1)
        kb.restore_layout(data)
        dev.finish()
        self.assertEqual(kb.slider_targets, [t])

    def test_absent_section_sends_nothing(self):
        kb, dev = vil_kb()
        kb.restore_layout(vil(kb, None))
        dev.finish()

    def test_invalid_sections_send_nothing_and_settings_restore(self):
        bad = [
            {"version": 1, "targets": [entry()] * 9},
            {"version": 1, "targets": [entry(control=128)]},
            {"version": 1, "targets": [entry(name="x" * 13)]},
            {"version": 1, "targets": [entry(colour="red")]},
        ]
        for section in bad:
            kb, dev = vil_kb()
            data = vil(kb, section, {"5": 9})
            with mock.patch.object(kb, "qmk_settings_set") as ms, \
                    mock.patch("editor.qmk_settings.QmkSettings.is_qsid_supported", return_value=True):
                with self.assertLogs("protocol.keyboard_comm", "WARNING"):
                    kb.restore_layout(data)
            dev.finish()
            ms.assert_called_once_with(5, 9)

    def test_keyboard_error_warns_and_settings_restore(self):
        kb, dev = vil_kb()
        data = vil(kb, {"version": 1, "targets": [entry(5, "#0a0b0c", "Pad")]}, {"5": 9})
        req = bytes([0x56, 0x03, 0, 5, 10, 11, 12]) + b"Pad".ljust(12, b"\x00")
        dev.expect(req, bytes([0x56, 0xFF]) + req[2:])
        with mock.patch.object(kb, "qmk_settings_set") as ms, \
                mock.patch("editor.qmk_settings.QmkSettings.is_qsid_supported", return_value=True):
            with self.assertLogs("protocol.keyboard_comm", "WARNING"):
                kb.restore_layout(data)
        dev.finish()
        ms.assert_called_once_with(5, 9)
