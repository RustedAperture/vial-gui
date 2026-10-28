import json
import struct
import unittest

from test.test_key_colours_protocol import make_kb, expect_reload, entry_bytes


def vil_kb():
    kb, dev = make_kb()
    colours = [[(1, 2, 3), None, (4, 5, 6)], [None, (7, 8, 9), None]]
    expect_reload(dev, 2, 3, colours)
    kb.reload_key_colours()
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
    return kb, dev, colours


def vil(kb, section):
    data = json.loads(kb.save_layout().decode("utf-8"))
    if section is None:
        data.pop("key_colours", None)
    else:
        data["key_colours"] = section
    return json.dumps(data).encode("utf-8")


def good():
    return {"version": 1, "layers": [["#010203", None, "#040506"], [None, "#070809", None]]}


class TestKeyColoursVil(unittest.TestCase):

    def test_save_includes_colours(self):
        kb, dev, colours = vil_kb()
        data = json.loads(kb.save_layout().decode("utf-8"))
        self.assertEqual(data["key_colours"], good())

    def test_save_omits_when_unsupported(self):
        kb, dev, colours = vil_kb()
        kb.key_colours_supported = False
        data = json.loads(kb.save_layout().decode("utf-8"))
        self.assertNotIn("key_colours", data)

    def test_restore_writes_matching(self):
        kb, dev, colours = vil_kb()
        for layer in range(2):
            req = struct.pack("BBBBB", 0x55, 0x03, layer, 0, 3) + entry_bytes(colours[layer])
            dev.expect(req, req)
        kb.restore_layout(vil(kb, good()))
        dev.finish()

    def test_restore_without_section_writes_nothing(self):
        kb, dev, _ = vil_kb()
        kb.restore_layout(vil(kb, None))
        dev.finish()

    def test_restore_unsupported_keyboard_ignores_section(self):
        kb, dev, _ = vil_kb()
        data = vil(kb, good())
        kb.key_colours_supported = False
        kb.restore_layout(data)
        dev.finish()

    def test_restore_bad_sections_write_nothing_and_do_not_raise(self):
        bad_sections = [
            {"version": 1, "layers": good()["layers"][:1]},
            {"version": 1, "layers": [["#010203", None], [None, None, None]]},
            {"version": 1, "layers": [["#010203", None, "#040506"], [None, "#-1-1-1", None]]},
            {"version": 1, "layers": [["#010203", None, "#040506"], [None, "#+1+1+1", None]]},
            {"version": 1, "layers": [["#010203", None, "#040506"], [None, "#12345g", None]]},
            {"version": 1, "layers": [["#010203", None, "#040506"], [None, 5, None]]},
            {"version": 1, "layers": [["#010203", None, "#040506"], "abc"]},
            {"version": 1, "layers": "abc"},
            {"version": 1, "layers": {"a": 1}},
            {"version": 1},
            {"version": 2, "layers": good()["layers"]},
            "junk",
            5,
        ]
        for section in bad_sections:
            kb, dev, _ = vil_kb()
            kb.restore_layout(vil(kb, section))
            dev.finish()

    def test_from_json_rejects_without_writing(self):
        kb, dev, _ = vil_kb()
        d = good()
        d["layers"][1][1] = "#-1-1-1"
        self.assertFalse(kb.key_colours_from_json(d))
        dev.finish()


if __name__ == "__main__":
    unittest.main()
