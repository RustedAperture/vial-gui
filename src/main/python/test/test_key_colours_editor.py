from kle_serial import Serial as KleSerial
from editor.key_colours import KeyColoursEditor, SWATCHES, BANNER_TEXT
from editor.layout_editor import LayoutEditor
from protocol.key_colours import LedInfo
from vial_device import VialKeyboard
from widgets.editor_container import EditorContainer

ORANGE = (0xff, 0x42, 0x00)


def make_keys():
    keys = []
    for key in KleSerial().deserialize([["0,0", "0,1", "0,2"]]).keys:
        row, col = key.labels[0].split(",")
        key.row, key.col = int(row), int(col)
        key.encoder_idx = key.encoder_dir = None
        key.layout_index = key.layout_option = -1
        keys.append(key)
    return keys


class FakeKeyboard:

    def __init__(self, supported=True, initialised=True, layers=2, leds=3):
        self.key_colours_supported = supported
        self.key_colours_layers = layers
        self.key_colours_led_count = leds
        self.key_colours_initialised = initialised
        self.key_colours = [[None] * leds for _ in range(layers)]
        self.leds = [LedInfo(i * 20, 0, 4, 0, i) for i in range(leds)]
        self.keys = make_keys()
        self.calls = []
        self.fail = False

    def set_key_colours(self, layer, changes):
        self.calls.append(("set", layer, dict(changes)))
        if self.fail:
            raise RuntimeError("boom")
        for led, c in changes.items():
            self.key_colours[layer][led] = c
        self.key_colours_initialised = True

    def set_key_colours_preview(self, layer):
        self.calls.append(("preview", layer))
        if self.fail:
            raise RuntimeError("boom")


def make_device(kb):
    dev = VialKeyboard.__new__(VialKeyboard)
    dev.keyboard = kb
    return dev


# pytest-qt only keeps weak references, so hold the containers for the whole session
all_containers = []


def make_editor(qtbot, kb=None):
    kb = kb or FakeKeyboard()
    editor = KeyColoursEditor(LayoutEditor())
    container = EditorContainer(editor)
    qtbot.addWidget(container)
    all_containers.append(container)
    editor.rebuild(make_device(kb))
    container.show()
    return editor, kb


def stroke(editor, *batches):
    for leds in batches:
        editor.widget.stroke_painted.emit(list(leds))
    editor.widget.stroke_finished.emit()


def sets(kb):
    return [c for c in kb.calls if c[0] == "set"]


def test_hidden_when_unsupported(qtbot):
    editor, kb = make_editor(qtbot, FakeKeyboard(supported=False))
    assert not editor.valid()
    editor.rebuild(None)
    assert not editor.valid()


def test_valid_when_supported(qtbot):
    editor, kb = make_editor(qtbot)
    assert editor.valid()
    assert [b.text() for b in editor.layer_buttons] == ["Layer 0", "Layer 1"]


def test_swatches():
    assert [s[0] for s in SWATCHES] == ["Orange", "Pink", "Purple", "Ice blue", "Green", "Red", "Yellow",
                                         "White", "Off"]
    assert SWATCHES[0][1] == "#ff4200" and SWATCHES[-1][1] == "#000000"


def test_brush_stroke_sends_each_led_and_undoes(qtbot):
    editor, kb = make_editor(qtbot)
    editor.set_brush_colour(ORANGE)
    stroke(editor, [0], [1])
    assert sets(kb) == [("set", 0, {0: ORANGE}), ("set", 0, {1: ORANGE})]
    assert editor.widget.colours == [ORANGE, ORANGE, None]
    assert editor.history.can_undo()
    assert editor.btn_undo.isEnabled()

    editor.on_undo()
    assert sets(kb)[-1] == ("set", 0, {0: None, 1: None})
    assert kb.key_colours[0] == [None, None, None]
    assert editor.widget.colours == [None, None, None]
    assert not editor.history.can_undo()
    assert not editor.btn_undo.isEnabled()


def test_eraser_sends_none(qtbot):
    kb = FakeKeyboard()
    kb.key_colours[0][2] = ORANGE
    editor, kb = make_editor(qtbot, kb)
    editor.set_tool("eraser")
    stroke(editor, [2])
    assert sets(kb) == [("set", 0, {2: None})]


def test_fill_sends_all_leds_once(qtbot):
    editor, kb = make_editor(qtbot)
    editor.set_brush_colour(ORANGE)
    editor.set_tool("fill")
    stroke(editor, [1], [2])
    assert sets(kb) == [("set", 0, {0: ORANGE, 1: ORANGE, 2: ORANGE})]
    editor.on_undo()
    assert sets(kb)[-1] == ("set", 0, {0: None, 1: None, 2: None})


def test_undo_writes_old_colours_on_its_layer(qtbot):
    kb = FakeKeyboard()
    kb.key_colours[1][0] = (1, 2, 3)
    editor, kb = make_editor(qtbot, kb)
    editor.set_layer(1)
    editor.set_brush_colour(ORANGE)
    stroke(editor, [0])
    editor.set_layer(0)
    editor.on_undo()
    assert sets(kb)[-1] == ("set", 1, {0: (1, 2, 3)})
    assert editor.layer == 1
    assert editor.layer_buttons[1].isChecked()
    # the undo itself is not recorded as a new stroke
    assert not editor.history.can_undo()


def test_activate_previews_and_deactivate_clears(qtbot):
    editor, kb = make_editor(qtbot)
    editor.activate()
    assert kb.calls[-1] == ("preview", 0)
    assert editor.preview_timer.isActive()
    assert editor.preview_timer.interval() == 1000
    editor.set_layer(1)
    assert kb.calls[-1] == ("preview", 1)
    editor.on_preview_timer()
    assert kb.calls[-1] == ("preview", 1)
    editor.deactivate()
    assert kb.calls[-1] == ("preview", None)
    assert not editor.preview_timer.isActive()


def test_layer_change_while_inactive_sends_no_preview(qtbot):
    editor, kb = make_editor(qtbot)
    editor.set_layer(1)
    assert [c for c in kb.calls if c[0] == "preview"] == []


def test_banner_only_when_uninitialised(qtbot):
    editor, kb = make_editor(qtbot)
    assert editor.banner.isHidden()
    editor, kb = make_editor(qtbot, FakeKeyboard(initialised=False))
    assert not editor.banner.isHidden()
    assert editor.banner_label.text() == BANNER_TEXT
    loads = []
    editor.load_requested.connect(lambda: loads.append(1))
    editor.btn_banner_load.click()
    assert loads == [1]
    # painting sets initialised, so the banner goes away
    editor.set_brush_colour(ORANGE)
    stroke(editor, [0])
    assert editor.banner.isHidden()


def test_save_load_buttons_emit(qtbot):
    editor, kb = make_editor(qtbot)
    got = []
    editor.save_requested.connect(lambda: got.append("save"))
    editor.load_requested.connect(lambda: got.append("load"))
    editor.btn_save.click()
    editor.btn_load.click()
    assert got == ["save", "load"]
    assert editor.btn_save.text() == "Save backup…"
    assert editor.btn_load.text() == "Load backup…"


def test_keyboard_errors_show_inline(qtbot):
    editor, kb = make_editor(qtbot)
    assert editor.error_label.isHidden()
    kb.fail = True
    editor.set_brush_colour(ORANGE)
    stroke(editor, [0])
    assert not editor.error_label.isHidden()
    editor.activate()
    editor.on_preview_timer()
    editor.deactivate()
    kb.fail = False
    stroke(editor, [1])
    assert editor.error_label.isHidden()


def test_lost_release_does_not_merge_strokes_or_block_undo(qtbot):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    editor, kb = make_editor(qtbot)
    w = editor.widget
    w.resize(w.sizeHint())
    editor.set_brush_colour(ORANGE)
    pos = [w._key_widgets[i].polygon.boundingRect().center().toPoint() for i in range(3)]
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, pos[0])
    # release lost; the next press must close the first stroke
    QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, pos[1])
    QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, pos[1])
    assert not editor.in_stroke
    editor.on_undo()
    assert sets(kb)[-1] == ("set", 0, {1: None})
    editor.on_undo()
    assert sets(kb)[-1] == ("set", 0, {0: None})


def test_write_error_survives_preview_ticks(qtbot):
    editor, kb = make_editor(qtbot)
    editor.activate()
    kb.fail = True
    editor.set_brush_colour(ORANGE)
    stroke(editor, [0])
    assert not editor.error_label.isHidden()
    kb.fail = False
    editor.on_preview_timer()
    editor.set_layer(1)
    assert kb.calls[-1] == ("preview", 1)
    assert not editor.error_label.isHidden()
    stroke(editor, [1])
    assert editor.error_label.isHidden()
    # a preview error alone is cleared by the next good preview
    kb.fail = True
    editor.on_preview_timer()
    assert not editor.error_label.isHidden()
    kb.fail = False
    editor.on_preview_timer()
    assert editor.error_label.isHidden()
    editor.deactivate()


def test_undo_error_survives_preview_ticks(qtbot):
    editor, kb = make_editor(qtbot)
    editor.set_brush_colour(ORANGE)
    stroke(editor, [0])
    editor.activate()
    kb.fail = True
    editor.on_undo()
    assert not editor.error_label.isHidden()
    kb.fail = False
    editor.on_preview_timer()
    assert not editor.error_label.isHidden()
    editor.deactivate()
